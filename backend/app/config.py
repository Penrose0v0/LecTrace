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
    # siliconflow（默认）/ openai / gemini，可插拔切换
    llm_provider: str = os.getenv("LLM_PROVIDER", "siliconflow")

    # SiliconFlow（默认；OpenAI 兼容协议）
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    siliconflow_model: str = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen3.5-122B-A10B")
    siliconflow_base_url: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

    # OpenAI（备选；实时转录 openai-stt 仍用这个 key）
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
    # Realtime 单会话 60 分钟上限：提前多久主动换一条会话（秒）
    openai_stt_rotate_sec: float = float(os.getenv("OPENAI_STT_ROTATE_SEC", str(50 * 60)))

    # Gemini（备选）
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # 讲义语言（转录内容的语言，默认日语）
    lecture_language: str = os.getenv("LECTURE_LANGUAGE", "ja")
    # 用户语言（摘要输出语言，默认日语）
    user_language: str = os.getenv("USER_LANGUAGE", "ja")

    # ---- 转录源 ----
    # 新建课堂的默认音频来源：google-stt（默认）/ openai-stt / replay（本地回放归档）
    transcription_source: str = os.getenv("TRANSCRIPTION_SOURCE", "google-stt")
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

    # ---- 录音保存 ----
    # off（默认）/ local（写到 RECORDINGS_DIR，开发用）/ gcs（写到 RECORDINGS_BUCKET）
    recordings: str = os.getenv("RECORDINGS", "off")
    recordings_dir: Path = ROOT_DIR / os.getenv("RECORDINGS_DIR", "data/recordings")
    recordings_bucket: str = os.getenv("RECORDINGS_BUCKET", "")

    # ---- 登录（Google Sign-In）----
    # OAuth 2.0 Web 客户端 ID（GCP Console → APIs & Services → Credentials）
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    # 会话 cookie 的签名密钥；生产必须设置（多实例 / 重启后登录态才不丢）
    session_secret: str = os.getenv("SESSION_SECRET", "")
    # 登录态有效期（天）
    session_days: int = int(os.getenv("SESSION_DAYS", "30"))
    # 允许登录的邮箱白名单（逗号分隔，不区分大小写）；留空 = 任何 Google 账号都能登
    allowed_emails: frozenset[str] = frozenset(
        e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()
    )

    # ---- 配额（管理员不受限；本地开发用户视为管理员）----
    admin_emails: frozenset[str] = frozenset(
        e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
    )
    # 单节课转录时长上限（分钟，0 = 不限）；暂停再继续算同一节
    quota_max_lecture_minutes: int = int(os.getenv("QUOTA_MAX_LECTURE_MINUTES", "105"))
    # 每天最多新建几节课（0 = 不限），按 quota_timezone 的自然日
    quota_max_lectures_per_day: int = int(os.getenv("QUOTA_MAX_LECTURES_PER_DAY", "3"))
    quota_timezone: str = os.getenv("QUOTA_TIMEZONE", "Asia/Tokyo")
    # 本地开发免 Google 登录：未配置 client id 且不在 Cloud Run 上时自动开启，
    # 也可用 AUTH_DEV_LOGIN=1/0 强制开/关
    _auth_dev_login_env: str = os.getenv("AUTH_DEV_LOGIN", "")
    on_cloud_run: bool = bool(os.getenv("K_SERVICE"))

    @property
    def auth_dev_login(self) -> bool:
        if self._auth_dev_login_env:
            return self._auth_dev_login_env.lower() in ("1", "true", "yes")
        return not self.google_client_id and not self.on_cloud_run

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def llm_configured(self) -> bool:
        return bool(
            {
                "siliconflow": self.siliconflow_api_key,
                "openai": self.openai_api_key,
                "gemini": self.gemini_api_key,
            }.get(self.llm_provider)
        )

    @property
    def llm_model(self) -> str:
        return {
            "siliconflow": self.siliconflow_model,
            "openai": self.openai_model,
            "gemini": self.gemini_model,
        }.get(self.llm_provider, "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
