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
1. 选一个归档课堂 → **开始转录**（默认 8× 加速回放真实日语讲义）。
2. 转录滚动几段后，随时拖动"最近 X 分钟"滑块，点 **没跟上？点我总结**。
3. 右侧出现 Gemini 生成的 Catchup 摘要。

> 调回放速度：改 `.env` 的 `REPLAY_SPEED`（越大越快），或前端 WS 带 `?speed=`。

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

## 三、从 demo 走向目标架构

代码里两处已做成可插拔，接真实服务时**上层不用改**：

- **转录源** `backend/app/transcription/`：现在是 `ReplaySource`。新增 `GoogleSTTSource`（前端经 WS 上行音频 → 后端代理 Speech-to-Text streaming），并把 `TRANSCRIPTION_SOURCE` 切到 `google-stt`。
- **存储** `backend/app/store/` 与 `conversations.py`：内存 / Firestore 两套实现已就绪，`STORE_BACKEND` 切换。转录源仍待接 STT。
