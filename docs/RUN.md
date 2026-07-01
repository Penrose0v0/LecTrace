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

## 二、部署到 Cloud Run

```bash
gcloud run deploy lectrace \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=你的key,GEMINI_MODEL=gemini-2.5-flash
```

`Dockerfile` 已把后端 + 前端 + 回放数据打进单容器，Cloud Run 注入的 `$PORT` 由 uvicorn 承接，WebSocket 长连接开箱可用。

## 三、从 demo 走向目标架构

代码里两处已做成可插拔，接真实服务时**上层不用改**：

- **转录源** `backend/app/transcription/`：现在是 `ReplaySource`。新增 `GoogleSTTSource`（前端经 WS 上行音频 → 后端代理 Speech-to-Text streaming），并把 `TRANSCRIPTION_SOURCE` 切到 `google-stt`。
- **存储** `backend/app/store/`：现在是 `MemoryStore`。新增 `FirestoreStore`（实现同一 `TranscriptStore` 接口），把 `STORE_BACKEND` 切到 `firestore`。
