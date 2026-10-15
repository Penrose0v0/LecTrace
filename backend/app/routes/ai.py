"""Catch-up 摘要 / 对话（都是 SSE 流式，结果挂在对话线程上）。

SSE 事件：meta → 多个默认 message（{"text": 片段}）→ done / error。
前置校验（会话 / 内容 / key）在开流前完成，便于用普通 HTTP 状态码反馈。
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .. import quota, usage
from ..ai import chat_stream, summarize_stream
from ..auth import current_user
from ..config import Settings, get_settings
from ..deps import SSE_HEADERS, get_store, sse
from ..llm import LLMError, LLMUsage
from ..models import Card, CatchupRequest, ChatRequest, Conversation, SessionInfo, User
from ..prompts import format_transcript, preset_message

router = APIRouter(prefix="/api", tags=["ai"])


async def _owned(session_id: str, user: User) -> SessionInfo:
    info = await get_store().get_session(session_id)
    if info is None:
        raise HTTPException(status_code=404, detail="讲义不存在。")
    if info.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权访问这节课。")
    return info


def _require_llm(settings: Settings) -> None:
    if not settings.llm_configured:
        raise HTTPException(status_code=502, detail="LLM 未配置 API key。")


async def _thread(session_id: str, conversation_id: str | None, title: str, created_t: float) -> Conversation:
    """取 / 建这节课的对话线程。"""
    store = get_store()
    if conversation_id:
        conv = await store.get_conversation(conversation_id)
        if conv is not None and conv.session_id == session_id:
            return conv
    return await store.create_conversation(session_id, title, created_t)


async def _chat_transcript(info: SessionInfo, settings: Settings) -> tuple[str, float]:
    """对话上下文：整节课从头到现在的转录（超长只留末尾）+ 当前课程时间。"""
    segs = await get_store().all_segments(info.id)
    now_t = segs[-1].t if segs else 0.0
    return format_transcript(segs, settings.chat_context_max_chars, info.user_language), now_t


@router.post("/catchup")
async def catchup(
    req: CatchupRequest, user: User = Depends(current_user), settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    store = get_store()
    info = await _owned(req.session_id, user)
    _require_llm(settings)
    window_minutes = float(req.window_minutes or info.window_minutes)
    now_t = await store.latest_t(info.id)
    if now_t <= 0:
        raise HTTPException(status_code=404, detail="还没有转录内容。")
    start_t = max(0.0, now_t - window_minutes * 60.0)
    segs = await store.window(info.id, start_t, now_t)
    if not segs:
        raise HTTPException(status_code=404, detail="该时间窗内没有转录内容。")

    index = await store.card_count(info.id) + 1
    card = Card(
        id=uuid.uuid4().hex, index=index,
        covered_from=start_t, covered_to=now_t, segment_count=len(segs),
        model=settings.llm_model,
        lecture_language=info.lecture_language, user_language=info.user_language,
        created_t=now_t,
    )
    conv = await _thread(info.id, req.conversation_id, f"Catch-up #{index}", now_t)

    async def gen():
        yield sse("meta", {
            "card_id": card.id, "index": index, "window_minutes": window_minutes,
            "covered_from": start_t, "covered_to": now_t, "segment_count": len(segs),
            "model": settings.llm_model,
            "conversation_id": conv.id, "conversation_title": conv.title,
        })
        acc, used, t0 = "", LLMUsage(), time.monotonic()
        try:
            async for chunk in summarize_stream(segs, window_minutes, info, settings, usage=used):
                acc += chunk
                yield sse(None, {"text": chunk})
        except LLMError as exc:
            yield sse("error", {"message": str(exc)})
            return
        card.summary = acc
        await store.add_card(info.id, card)
        conv.messages.append({
            "role": "assistant", "kind": "catchup", "content": acc,
            "card_id": card.id, "index": index,
            "covered_from": start_t, "covered_to": now_t, "segment_count": len(segs),
        })
        await store.save_conversation(conv)
        await usage.record_llm(store, user, settings, info.id, "catchup", used, time.monotonic() - t0)
        yield sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user: User = Depends(current_user)) -> dict:
    conv = await get_store().get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="对话不存在。")
    await _owned(conv.session_id, user)
    return conv.model_dump()


@router.post("/chat")
async def chat(
    req: ChatRequest, user: User = Depends(current_user), settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """结合整节课转录的多轮对话。preset=explain 等快捷指令由服务端按用户语言生成消息。

    每条消息记下发出时的课程时间 t，拼 prompt 时标在历史里，模型才分得清
    「上次回答时老师讲到哪」和「现在讲到哪」。
    """
    store = get_store()
    info = await _owned(req.session_id, user)
    _require_llm(settings)
    await quota.check_can_chat(store, user, settings)
    message = req.message.strip()
    if req.preset:
        message = preset_message(req.preset, info.user_language) or ""
        if not message:
            raise HTTPException(status_code=400, detail="未知的快捷指令。")
    if not message:
        raise HTTPException(status_code=400, detail="消息为空。")

    transcript, now_t = await _chat_transcript(info, settings)
    conv = await _thread(info.id, req.conversation_id, message[:24], now_t)
    conv.messages.append({"role": "user", "content": message, "t": now_t})

    async def gen():
        yield sse("meta", {"conversation_id": conv.id, "title": conv.title, "user_message": message})
        acc, used, t0 = "", LLMUsage(), time.monotonic()
        try:
            async for chunk in chat_stream(conv.messages, transcript, now_t, info, settings, usage=used):
                acc += chunk
                yield sse(None, {"text": chunk})
        except LLMError as exc:
            yield sse("error", {"message": str(exc)})  # 失败不持久化这一轮，也不计入当日配额
            return
        conv.messages.append({"role": "assistant", "content": acc, "t": now_t})
        await store.save_conversation(conv)
        await usage.record_llm(store, user, settings, info.id, "chat", used, time.monotonic() - t0)
        yield sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
