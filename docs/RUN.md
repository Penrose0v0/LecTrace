# 本地运行 & 部署

## 一、本地跑 demo

### 1. 填 Gemini key
在仓库根的 `.env` 里填上（从 https://aistudio.google.com/apikey 申请）：

```
GEMINI_API_KEY=你的key
```

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
   来源选「回放归档」可以不用麦克风（默认 8× 加速回放真实日语讲义）。
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

> 数据归属：讲义（`sessions/{id}`）带 `user_id`，列表 / 详情 / WebSocket / Catch-up / 对话都校验归属。
> 用户偏好存在 `users/{user_id}`。

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

## 二、部署到 Cloud Run

```bash
gcloud run deploy lectrace \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=你的key,GEMINI_MODEL=gemini-2.5-flash
```

`Dockerfile` 已把后端 + 前端 + 回放数据打进单容器，Cloud Run 注入的 `$PORT` 由 uvicorn 承接，WebSocket 长连接开箱可用。

要在 Cloud Run 上开持久化，追加 `STORE_BACKEND=firestore,GCP_PROJECT=<项目>`，并确保运行时服务账号有 `roles/datastore.user`（访问 Firestore，无需 key 文件）。

登录相关必须追加 `GOOGLE_CLIENT_ID=<client id>,SESSION_SECRET=<随机串>`：Cloud Run 上不会开本地开发登录，
缺 client id 时登录页没有任何可点的按钮；缺 `SESSION_SECRET` 时每个实例各自随机签名，多实例 / 重启会掉登录态。

> 当前线上（2026-10 查看）还没有这两个变量，下次部署记得带上。

## 三、从 demo 走向目标架构

代码里两处已做成可插拔，接真实服务时**上层不用改**：

- **转录源** `backend/app/transcription/`：现在是 `ReplaySource`。新增 `GoogleSTTSource`（前端经 WS 上行音频 → 后端代理 Speech-to-Text streaming），并把 `TRANSCRIPTION_SOURCE` 切到 `google-stt`。
- **存储** `backend/app/store/` 与 `conversations.py`：内存 / Firestore 两套实现已就绪，`STORE_BACKEND` 切换。转录源仍待接 STT。
