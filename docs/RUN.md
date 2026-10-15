# 本地运行 & 部署

## 一、本地跑 demo

### 1. 填 LLM key
在仓库根的 `.env` 里填上（SiliconFlow，从 https://cloud.siliconflow.cn 申请）：

```
SILICONFLOW_API_KEY=你的key
```

默认模型 `deepseek-ai/DeepSeek-V4-Flash`（2026-10 换的：`Qwen/Qwen3.5-122B-A10B` 长期 503 "System is too busy"）。
Catch-up 和对话都固定 `enable_thinking=false`：开思考模型会把预算用满，首 token 20–80 秒，等不起。
`CHAT_THINKING=1` 可给对话开思考（预算 `CHAT_THINKING_BUDGET`，默认 1024）。
对话上下文是整节课的转录（`CHAT_CONTEXT_MAX_CHARS`，默认 4 万字，超了只留末尾）。
注意 `zai-org/GLM-5.3-Flash` 不认 `enable_thinking=false`，别用。
OpenAI / Gemini 的实现还在（`LLM_PROVIDER=openai|gemini`），只是暂不使用；麦克风转录仍走 OpenAI，所以 `OPENAI_API_KEY` 要保留。
其余默认值即可（`replay` 转录源 + 内存存储）。

### 2. 装依赖（venv 已就绪则可跳过）

```bash
.venv/bin/pip install -r backend/requirements.txt
```

### 3. 启动

```bash
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

打开 http://127.0.0.1:8000 ：
1. 登录页：本地没配 `GOOGLE_CLIENT_ID` 时显示「以本地开发身份继续」，点它进入。
2. 新建课堂时 meta 面板默认展开：填标题 / 描述、讲义语言、你的语言、Catch-up 时长；
   默认来源是「麦克风 · Google」（本地需要先 `gcloud auth application-default login`）；
   来源选「回放归档」可以不用麦克风（默认 8× 加速回放真实日语讲义）。回放归档只在本地有：
   `_archive/data` 不进镜像，线上没有归档文件时前端会自动隐藏这个选项。
3. 按 ● 开始，面板自动收起、转录开始滚动。右侧 **Catch-up** 总结最近 X 分钟，
   **Explain** 解释老师刚才提到的术语，输入框可以自由提问；结果都挂在对话线程里，
   点 Catch-up 结果上方的时间范围会在转录里高亮对应段落。
4. 左侧「历史」能回看过去的课堂；打开后按 ▶ 可以续接转录（回放课不能续接）。

> 调回放速度：改 `.env` 的 `REPLAY_SPEED`（越大越快），或前端 WS 带 `?speed=`。

## 一·三、Google 登录

本地开发可以一直用「本地开发登录」。要用真实 Google 账号（线上必须）：

1. GCP Console → **APIs & Services → OAuth consent screen**：建一个 External 应用（测试阶段把自己的邮箱加进 Test users）。
2. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application**，
   Authorized JavaScript origins 填：
   - `http://localhost:8000` 和 `http://127.0.0.1:8000`（本地）
   - `https://lectrace-jngknpqwya-an.a.run.app`（Cloud Run）
   不需要 redirect URI（前端用的是 Google Identity Services 弹窗模式）。
3. 把 client id 填进 `.env` 的 `GOOGLE_CLIENT_ID`；再生成一个 `SESSION_SECRET`（`openssl rand -hex 32`）。
4. 个人使用建议设 `ALLOWED_EMAILS=你的邮箱`，否则任何 Google 账号都能登录并消耗 LLM 额度。

### 给别人用：配额

把自己放进 `ADMIN_EMAILS`（不受限），其他登录用户默认受两条限制，都在 `.env` 里调，0 = 不限：

- `QUOTA_MAX_LECTURE_MINUTES=105`（1 小时 45 分）：单节课转录时长上限，暂停再继续算同一节。到点服务端停止收音、
  冲完尾段后发 `limit` 消息，前端进入暂停并提示；再按继续会立刻被拒。
- `QUOTA_MAX_LECTURES_PER_DAY=3`：每天最多新建几节课，按 `QUOTA_TIMEZONE`（默认 Asia/Tokyo）的自然日，
  超过时新建返回 429。登录响应里的 `quota` 字段给前端显示"今天 n/3 节"。
- `QUOTA_MAX_CHATS_PER_DAY=30`：每天最多发几条 AI 对话（只数成功回复的；LLM 报错那次不算）。超过时
  `/api/chat` 返回 429 `quota_chats_per_day`，前端在气泡里提示。Catch-up 不计入：每次只有 160 token 输出，
  而对话每次要把整节课转录（最多 4 万字）塞进上下文，是 LLM 开销的大头。默认 30 是占位值，按预算调。

本地开发用户在 `ADMIN_EMAILS` 为空时视为管理员；想本地测配额就随便填一个别的邮箱进去。

> 数据归属：讲义（`sessions/{id}`）带 `user_id`，列表 / 详情 / WebSocket / Catch-up / 对话都校验归属。
> 用户偏好存在 `users/{user_id}`。

### 看每个人用了多少：用量后台

管理员登录后，头像菜单里有「用量后台」，或直接开 `/admin.html`（同一个登录 cookie，非管理员 403）。
每个用户一行：首次登录、最近活跃、登录次数、课堂数、转录时长、Catch-up / 对话次数、LLM 输入 / 输出 token、
估算成本；点一行展开最近 30 天的每日数字和最近 40 条明细（每次 LLM 调用的 token、每段转录连接的秒数）。

数据怎么来的（`backend/app/usage.py`）：

- 登录 / 刷新页面 → `users/{uid}` 写入 email、name、picture、`last_seen_at`；真正登录还加 `login_count`、`first/last_login_at`。
- 转录 WebSocket 断开 → 本次收音秒数累加到 `stt_seconds`（暂停期间不连，不算；回放来源不走 STT，不记）。
- 每次 Catch-up / 对话成功 → 从流式响应末尾取 `usage`（OpenAI 协议加了 `stream_options.include_usage`；Gemini 读 `usageMetadata`）累加 token。
- 累计写在 `users/{uid}.usage`，当日写在 `users/{uid}/days/{YYYY-MM-DD}`（对话配额就从这里数），明细在 `users/{uid}/events`。

成本估算只是乘单价：`LLM_PRICE_INPUT_PER_M` / `LLM_PRICE_OUTPUT_PER_M`（每百万 token）、`STT_PRICE_PER_MIN`
（Google STT v1 标准模型约 0.024 USD/分），货币标签 `COST_CURRENCY`。LLM 单价默认 0，换模型后记得改；
真实账单以 GCP / SiliconFlow 控制台为准，这里只能分到人头做参考。

## 一·五、启用 Firestore 持久化（可选）

默认 `STORE_BACKEND=memory`，重启即丢。切到 Firestore 后，**Catchup 卡片 / AI 对话 / 转录段落**都会持久化，重启或多实例都不丢。

### 本地用模拟器测试（零凭证）

需要 JDK 11+（本机用 `brew install openjdk@17`）。

```bash
# 1. 起模拟器
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
firebase emulators:start --only firestore --project demo-lectrace   # 监听 127.0.0.1:8080/8410

# 2. 另开一个终端，指向模拟器启动后端
export STORE_BACKEND=firestore
export GCP_PROJECT=demo-lectrace
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8410
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

### 生产（真实 Firestore）

```bash
# 1. 在项目里创建 Firestore 数据库（一次性，二选一）
gcloud firestore databases create --location=asia-northeast1

# 2. 配置本地 ADC 凭证
gcloud auth application-default login

# 3. 启动（不要设 FIRESTORE_EMULATOR_HOST）
export STORE_BACKEND=firestore
export GCP_PROJECT=$(gcloud config get-value project)
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

> 数据模型：`sessions/{id}`（含 `segments/*`、`cards/*` 子集合）、`conversations/{id}`。
> Cloud Run 上用服务账号即可访问 Firestore，无需 key 文件。

## 一·七、录音保存（可选）

麦克风上行的原始 PCM 可以顺手存下来（回放功能以后再做，数据先留着）。每次连接是一个 take
（暂停再继续就是下一个），元信息（采样率、对应转录时间轴的 `t_offset`、时长）记在课堂文档的 `recordings` 里。

- 本地：`RECORDINGS=local`，文件写到 `data/recordings/sessions/{id}/take-000.pcm`（已 gitignore）。
- 线上：`RECORDINGS=gcs` + `RECORDINGS_BUCKET=lectrace-recordings`，运行时服务账号需要
  `roles/storage.objectCreator`（只写）：

```bash
gcloud storage buckets create gs://lectrace-recordings --location=asia-northeast1 --uniform-bucket-level-access
gcloud storage buckets add-iam-policy-binding gs://lectrace-recordings \
  --member=serviceAccount:176778301118-compute@developer.gserviceaccount.com --role=roles/storage.objectCreator
```

> 存的是无头 PCM（16-bit 单声道，采样率见元信息）：长度事先不知道而 GCS 对象不可修改，没法回填 WAV 头。
> 回放时按对象大小拼一个 WAV 头即可。一小时约 170 MB。

## 二、部署到 Cloud Run

```bash
gcloud run deploy lectrace \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars SILICONFLOW_API_KEY=你的key,OPENAI_API_KEY=转录用的key
```

`Dockerfile` 已把后端 + 前端 + 回放数据打进单容器，Cloud Run 注入的 `$PORT` 由 uvicorn 承接，WebSocket 长连接开箱可用。

**整节课不中断的三道保险**（都已内置，不用配）：
- OpenAI Realtime 单会话最长 60 分钟 → 后端每 50 分钟主动换一条上游会话（`OPENAI_STT_ROTATE_SEC`），上游意外断开也自动重连，音频在队列里不丢。
- Cloud Run 单请求最长 60 分钟（部署时 `--timeout=3600`）→ 前端每 55 分钟主动换一条 WebSocket 续接同一 session。
- 服务端每 20 秒发心跳 → 前端 45 秒没收到任何消息就判定死连接、自动重连。

要在 Cloud Run 上开持久化，追加 `STORE_BACKEND=firestore,GCP_PROJECT=<项目>`，并确保运行时服务账号有 `roles/datastore.user`（访问 Firestore，无需 key 文件）。

登录相关必须追加 `GOOGLE_CLIENT_ID=<client id>,SESSION_SECRET=<随机串>`：Cloud Run 上不会开本地开发登录，
缺 client id 时登录页没有任何可点的按钮；缺 `SESSION_SECRET` 时每个实例各自随机签名，多实例 / 重启会掉登录态。

> 当前线上（2026-10 查看）还没有这两个变量，下次部署记得带上。

## 三、后端代码地图

```
backend/app/
├── main.py            装配路由 + 前端静态托管
├── config.py          全部环境变量
├── auth.py            Google ID token 校验、签名 cookie、current_user 依赖
├── deps.py            store 单例、owned_session 依赖、SSE 小工具
├── recording.py       录音落盘（本地目录 / GCS 流式上传），独立线程写入
├── models.py          pydantic 数据结构（Segment / Card / LectureMeta / SessionInfo / Conversation / ...）
├── prompts/           ★ 所有 prompt：ja.toml / zh.toml / en.toml 按用户语言各一份（key 相同），
│                        __init__.py 只负责加载和填充。改措辞只改 toml；加语言就加一个文件
├── ai.py              摘要 / 对话服务层：prompts → llm
├── llm/               LLM_PROVIDER 可插拔：base（协议 + SSE 工具）/ openai / gemini
├── store/             STORE_BACKEND 可插拔：base（协议）/ memory / firestore，含会话、段落、卡片、对话、偏好
├── transcription/     replay / openai_stt / google_stt + make_stt_runner 工厂
└── routes/            auth / lectures / ai（catchup + chat）/ transcribe（WebSocket）
```

想换 LLM：在 `llm/` 加一个 provider 类，`get_llm` 里注册。想换 STT：在 `transcription/` 加一个
`run_stt(audio_queue, lang, on_interim, on_final)`，`make_stt_runner` 里注册。
