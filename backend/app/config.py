"""集中管理运行配置，全部来自环境变量（本地经 .env 注入）。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# 仓库根目录：backend/app/config.py -> parents[2]
ROOT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")


class Settings:
    # ---- Gemini（Catchup 摘要） ----
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # 讲义语言（转录内容的语言，默认日语）
    lecture_language: str = os.getenv("LECTURE_LANGUAGE", "ja")
    # 用户语言（摘要输出语言，默认日语）
    user_language: str = os.getenv("USER_LANGUAGE", "ja")

    # ---- 转录源 ----
    # demo 阶段：replay（回放归档 session）。之后可换 google-stt。
    transcription_source: str = os.getenv("TRANSCRIPTION_SOURCE", "replay")
    # 归档数据目录（回放用）
    demo_data_dir: Path = ROOT_DIR / os.getenv("DEMO_DATA_DIR", "_archive/data")
    # 回放加速倍率：8 表示 1 小时讲义 ~7.5 分钟放完
    replay_speed: float = float(os.getenv("REPLAY_SPEED", "8"))
    # 单段之间最长等待（秒），避免真实长停顿把 demo 卡住
    replay_max_gap_sec: float = float(os.getenv("REPLAY_MAX_GAP_SEC", "2.0"))

    # ---- 存储 ----
    # demo 阶段：memory。之后可换 firestore。
    store_backend: str = os.getenv("STORE_BACKEND", "memory")

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
