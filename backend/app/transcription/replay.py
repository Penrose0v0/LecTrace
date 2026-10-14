"""回放归档 session，模拟实时转录流（demo 用）。

归档格式（旧数据）：{"lines": [{"seq", "text", "t", "wall_time"}, ...]}
其中 t 是距讲义开始的秒数——直接当逻辑时间轴。回放时按相邻段落的 t 差 / 加速倍率
睡眠，从而在几分钟内“重演”一小时的讲义。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..models import Segment


def list_demo_sessions(data_dir: Path) -> list[dict]:
    """列出可回放的归档 session（供前端选择）。"""
    out: list[dict] = []
    if not data_dir.exists():
        return out
    for f in sorted(data_dir.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        lines = d.get("lines", [])
        out.append(
            {
                "file": f.name,
                "duration_sec": d.get("duration_sec"),
                "line_count": len(lines),
            }
        )
    return out


def _load_segments(path: Path) -> list[Segment]:
    d = json.loads(path.read_text(encoding="utf-8"))
    segs: list[Segment] = []
    for line in d.get("lines", []):
        text = (line.get("text") or "").strip()
        if not text:
            continue
        segs.append(Segment(seq=line["seq"], text=text, t=float(line["t"])))
    return segs


class ReplaySource:
    def __init__(
        self,
        path: Path,
        speed: float = 8.0,
        max_gap_sec: float = 2.0,
        start_after_t: float = 0.0,
    ) -> None:
        self._path = path
        self._speed = max(speed, 0.1)
        self._max_gap = max_gap_sec
        self._start_after_t = start_after_t  # 续播：只推 t 大于此值的段落
        self.segments = _load_segments(path)

    async def stream(self):
        prev_t = self._start_after_t
        for seg in self.segments:
            if seg.t <= self._start_after_t:
                continue
            gap = max(0.0, seg.t - prev_t) / self._speed
            await asyncio.sleep(min(gap, self._max_gap))
            prev_t = seg.t
            yield seg
