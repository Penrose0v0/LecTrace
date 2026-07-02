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
    # ---- LLM 提供方（Catchup 摘要 + AI 对话）----
    # openai（默认）或 gemini，可插拔切换
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")

    # OpenAI（默认）
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    # OpenAI 实时转录模型（source=openai-stt 时用）。
    # gpt-realtime-whisper 是原生流式模型，适合连续讲课；gpt-4o(-mini)-transcribe
    # 是非流式模型，塞进实时会话会把连续语音切成碎片并幻觉。
    openai_stt_model: str = os.getenv("OPENAI_STT_MODEL", "gpt-realtime-whisper")
    # VAD 静音阈值(ms)：调大避免讲课停顿被切成碎片（默认 200ms 会碎片+幻觉）
    openai_stt_silence_ms: int = int(os.getenv("OPENAI_STT_SILENCE_MS", "800"))
    # whisper 无 VAD，需定期 commit 才定稿；每多少毫秒提交一次
    openai_stt_commit_ms: int = int(os.getenv("OPENAI_STT_COMMIT_MS", "4000"))

    # Gemini（备选）
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
    # demo 阶段：memory。持久化用 firestore。
    store_backend: str = os.getenv("STORE_BACKEND", "memory")
    # Firestore 项目 / 数据库（store_backend=firestore 时用）
    gcp_project: str = os.getenv("GCP_PROJECT", "") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    firestore_database: str = os.getenv("FIRESTORE_DATABASE", "(default)")

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        return bool(self.gemini_api_key)

    @property
    def llm_model(self) -> str:
        return self.openai_model if self.llm_provider == "openai" else self.gemini_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
