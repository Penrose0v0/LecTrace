"""讲义（session）的增查改 + 归档列表。"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from .. import quota
from ..auth import current_user
from ..config import Settings, get_settings
from ..deps import get_store, owned_session
from ..models import LANGS, SOURCES, LectureMeta, LectureUpdate, SessionInfo, User
from ..recording import delete_recordings
from ..transcription import list_demo_sessions

router = APIRouter(prefix="/api", tags=["lectures"])


def _validate(meta: LectureMeta | LectureUpdate) -> None:
    if meta.lecture_language is not None and meta.lecture_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的讲义语言。")
    if meta.user_language is not None and meta.user_language not in LANGS:
        raise HTTPException(status_code=400, detail="不支持的用户语言。")
    if meta.source is not None and meta.source not in SOURCES:
        raise HTTPException(status_code=400, detail="不支持的转录来源。")


@router.get("/demo-sessions")
def demo_sessions(_: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> dict:
    """可回放的归档 session 列表（demo / 本地测试用）。"""
    return {"sessions": list_demo_sessions(settings.demo_data_dir)}


@router.post("/sessions")
async def create_session(
    meta: LectureMeta, user: User = Depends(current_user), settings: Settings = Depends(get_settings)
) -> dict:
    _validate(meta)
    store = get_store()
    await quota.check_can_create_lecture(store, user, settings)
    session_id = uuid.uuid4().hex
    await store.create_session(session_id, {"user_id": user.id, **meta.model_dump()})
    info = await store.get_session(session_id)
    return info.model_dump() if info else {"id": session_id}


@router.get("/sessions")
async def list_sessions(user: User = Depends(current_user)) -> dict:
    return {"sessions": [s.model_dump() for s in await get_store().list_sessions(user.id)]}


@router.get("/sessions/{session_id}")
async def get_session(info: SessionInfo = Depends(owned_session)) -> dict:
    """讲义详情 + 全部转录（回看 / resume 用）。"""
    segs = await get_store().all_segments(info.id)
    return {"session": info.model_dump(), "segments": [s.model_dump() for s in segs]}


@router.patch("/sessions/{session_id}")
async def update_session(patch: LectureUpdate, info: SessionInfo = Depends(owned_session)) -> dict:
    _validate(patch)
    store = get_store()
    data = patch.model_dump(exclude_none=True)
    if data:
        await store.update_session(info.id, data)
    updated = await store.get_session(info.id)
    return updated.model_dump() if updated else {}


@router.delete("/sessions/{session_id}")
async def delete_session(
    info: SessionInfo = Depends(owned_session), settings: Settings = Depends(get_settings)
) -> dict:
    """删掉整节课：转录、Catch-up、对话线程、录音文件。不可恢复。"""
    await get_store().delete_session(info.id)
    if info.recordings:
        await asyncio.to_thread(delete_recordings, settings, info.recordings)
    return {"ok": True}


@router.get("/sessions/{session_id}/cards")
async def list_cards(info: SessionInfo = Depends(owned_session)) -> dict:
    """该会话已生成的 Catchup 卡片。"""
    return {"cards": [c.model_dump() for c in await get_store().list_cards(info.id)]}


@router.get("/sessions/{session_id}/conversations")
async def list_conversations(info: SessionInfo = Depends(owned_session)) -> dict:
    return {"conversations": [c.summary() for c in await get_store().list_conversations(info.id)]}
