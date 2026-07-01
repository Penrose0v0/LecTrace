"""Firestore 版存储：转录段落 + 会话元数据 + Catchup 卡片。

数据模型：
  sessions/{session_id}
    ├─ (doc fields) file, created_at
    ├─ segments/{seq}   {seq, text, t}
    └─ cards/{card_id}  {index, covered_from, covered_to, segment_count,
                         model, lecture_language, user_language, summary, created_t}

用 AsyncClient，全程 await，不阻塞事件循环。设置 FIRESTORE_EMULATOR_HOST 即连模拟器。
"""

from __future__ import annotations

from google.cloud import firestore

from ..models import Card, Segment


class FirestoreStore:
    def __init__(self, project: str | None = None, database: str = "(default)") -> None:
        kwargs: dict = {"database": database}
        if project:
            kwargs["project"] = project
        self._db = firestore.AsyncClient(**kwargs)

    def _session(self, session_id: str):
        return self._db.collection("sessions").document(session_id)

    async def create_session(self, session_id: str, meta: dict | None = None) -> None:
        data = {"created_at": firestore.SERVER_TIMESTAMP, **(meta or {})}
        await self._session(session_id).set(data, merge=True)

    async def append(self, session_id: str, segment: Segment) -> None:
        await self._session(session_id).collection("segments").document(
            str(segment.seq)
        ).set({"seq": segment.seq, "text": segment.text, "t": segment.t})

    async def latest_t(self, session_id: str) -> float:
        segs = self._session(session_id).collection("segments")
        q = segs.order_by("t", direction=firestore.Query.DESCENDING).limit(1)
        async for doc in q.stream():
            return float(doc.get("t"))
        return 0.0

    async def window(self, session_id: str, start_t: float, end_t: float) -> list[Segment]:
        segs = self._session(session_id).collection("segments")
        q = (
            segs.where(filter=firestore.FieldFilter("t", ">=", start_t))
            .where(filter=firestore.FieldFilter("t", "<=", end_t))
            .order_by("t")
        )
        out: list[Segment] = []
        async for doc in q.stream():
            d = doc.to_dict()
            out.append(Segment(seq=d["seq"], text=d["text"], t=d["t"]))
        return out

    async def add_card(self, session_id: str, card: Card) -> None:
        await self._session(session_id).collection("cards").document(card.id).set(
            {
                "index": card.index,
                "covered_from": card.covered_from,
                "covered_to": card.covered_to,
                "segment_count": card.segment_count,
                "model": card.model,
                "lecture_language": card.lecture_language,
                "user_language": card.user_language,
                "summary": card.summary,
                "created_t": card.created_t,
            }
        )

    async def list_cards(self, session_id: str) -> list[Card]:
        cards = self._session(session_id).collection("cards").order_by("index")
        out: list[Card] = []
        async for doc in cards.stream():
            d = doc.to_dict()
            out.append(Card(id=doc.id, **d))
        return out

    async def card_count(self, session_id: str) -> int:
        # 卡片数量很小，直接数
        count = 0
        async for _ in self._session(session_id).collection("cards").stream():
            count += 1
        return count

    async def all_segments(self, session_id: str) -> list[Segment]:
        segs = self._session(session_id).collection("segments").order_by("t")
        out: list[Segment] = []
        async for doc in segs.stream():
            d = doc.to_dict()
            out.append(Segment(seq=d["seq"], text=d["text"], t=d["t"]))
        return out
