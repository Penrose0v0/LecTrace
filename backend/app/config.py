"""集中管理运行配置，全部来自环境变量（本地经 .env 注入）。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# 仓库根目录：backend/app/config.py -> parents[2]
ROOT_DIR = Path(__file__).resolve().parents[2]

# 本地让 .env 覆盖进程环境：uvicorn --reload 的 worker 会继承首次加载时的环境变量，
# 不覆盖的话改了 .env 要完整重启才生效。Cloud Run 上没有 .env，环境变量以平台配置为准
load_dotenv(ROOT_DIR / ".env", override=not os.getenv("K_SERVICE"))


class Settings:
    # ---- LLM 提供方（Catchup 摘要 + AI 对话）----
    # siliconflow（默认）/ openai / gemini，可插拔切换
    llm_provider: str = os.getenv("LLM_PROVIDER", "siliconflow")

    # SiliconFlow（默认；OpenAI 兼容协议）
    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    # 2026-10 实测：Qwen3.5-122B-A10B 长期 503；DeepSeek-V4-Flash 首 token 1–2s，不开思考也能按规则答题
    siliconflow_model: str = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
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

    # ---- AI 对话 ----
    # 对话是否允许模型先推理再作答（Catch-up 永远不开）。默认关：实测开了首 token 要 20–80 秒，
    # 因为模型会把思考预算用满；关掉后 1–2 秒，prompt 写清楚规则后质量够用
    chat_thinking: bool = os.getenv("CHAT_THINKING", "0").lower() in ("1", "true", "yes")
    # 思考预算（token），仅 CHAT_THINKING=1 时生效
    chat_thinking_budget: int = int(os.getenv("CHAT_THINKING_BUDGET", "1024"))
    # 对话上下文里放多少转录（字符）。整节课从头到现在都给，超了只保留末尾。
    # 实测 Google STT 日语课约 250–350 字/分钟，105 分钟 ≈ 3.5 万字，默认值能装下一整节
    chat_context_max_chars: int = int(os.getenv("CHAT_CONTEXT_MAX_CHARS", "40000"))
    # 讲义语言（转录内容的语言，默认日语）
    lecture_language: str = os.getenv("LECTURE_LANGUAGE", "ja")
    # 用户语言（摘要输出语言，默认日语）
    user_language: str = os.getenv("USER_LANGUAGE", "ja")

    # ---- 转录源 ----
    # 新建课堂的默认音频来源：google-stt（v1 default）/ google-stt-v2（Chirp 3）/ openai-stt / replay（本地回放归档）
    transcription_source: str = os.getenv("TRANSCRIPTION_SOURCE", "google-stt")
    # Google STT v2：区域 + 模型。chirp_3 的日语 2026-10 只在 us / eu 可用（asia-northeast1 拒绝），
    # 音频会送去该区域处理。recognizer 用隐式 "_"，项目 ID 取 GCP_PROJECT
    google_stt_v2_location: str = os.getenv("GOOGLE_STT_V2_LOCATION", "us")
    google_stt_v2_model: str = os.getenv("GOOGLE_STT_V2_MODEL", "chirp_3")
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

    # ---- 域名迁移：旧域名 → 新域名的无感登录（见 auth.py / routes/auth.py 的 handoff）----
    # 新域名（不带协议）。留空 = 功能关闭：不跳转、handoff 接口 404，随时可回滚
    primary_host: str = os.getenv("PRIMARY_HOST", "").strip().lower()
    # 旧域名列表（逗号分隔）。只有这些 host 上的页面会把已登录用户迁到 PRIMARY_HOST
    legacy_hosts: frozenset[str] = frozenset(
        h.strip().lower() for h in os.getenv("LEGACY_HOSTS", "").split(",") if h.strip()
    )
    # Cloudflare Worker 与后端的共享密钥：Worker 在 X-Proxy-Auth 头里带上，后端才信任 X-Forwarded-Host。
    # 不配则一律按 Host 头判断（直连 Cloud Run 时就是 run.app 域名）
    proxy_shared_secret: str = os.getenv("PROXY_SHARED_SECRET", "")
    # 迁移票据有效期（秒），一次性
    handoff_ttl_sec: int = int(os.getenv("HANDOFF_TTL_SEC", "60"))

    @property
    def handoff_enabled(self) -> bool:
        return bool(self.primary_host)

    # ---- 配额（管理员不受限；本地开发用户视为管理员）----
    admin_emails: frozenset[str] = frozenset(
        e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
    )
    # 单节课转录时长上限（分钟，0 = 不限）；暂停再继续算同一节
    quota_max_lecture_minutes: int = int(os.getenv("QUOTA_MAX_LECTURE_MINUTES", "105"))
    # 每天最多新建几节课（0 = 不限），按 quota_timezone 的自然日
    quota_max_lectures_per_day: int = int(os.getenv("QUOTA_MAX_LECTURES_PER_DAY", "3"))
    # 每天最多发几条 AI 对话（0 = 不限）。Catch-up 不计：每次只有 160 token 输出，且已被课时上限约束。
    # 对话一次要带整节课转录（最多 4 万字）进上下文，是 LLM 开销的大头。默认值是占位，按预算调
    quota_max_chats_per_day: int = int(os.getenv("QUOTA_MAX_CHATS_PER_DAY", "30"))
    quota_timezone: str = os.getenv("QUOTA_TIMEZONE", "Asia/Tokyo")

    # ---- 成本估算（后台用量页显示；0 = 不估算，只记 token / 秒数）----
    # LLM 单价：每百万 token（输入 / 输出），按 LLM_PROVIDER 当前模型填
    llm_price_input_per_m: float = float(os.getenv("LLM_PRICE_INPUT_PER_M", "0"))
    llm_price_output_per_m: float = float(os.getenv("LLM_PRICE_OUTPUT_PER_M", "0"))
    # 语音转录单价：每分钟。Google STT v1 标准模型 0.024 USD/分；v2（Chirp 3 等）0.016 USD/分
    stt_price_per_min: float = float(os.getenv("STT_PRICE_PER_MIN", "0.024"))
    stt_v2_price_per_min: float = float(os.getenv("STT_V2_PRICE_PER_MIN", "0.016"))
    # 只是显示用的货币标签，所有单价得用同一种货币
    cost_currency: str = os.getenv("COST_CURRENCY", "USD")
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
