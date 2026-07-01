# LecTrace —— 单容器（后端 API + WS + 前端静态），部署到 Cloud Run
FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend
# demo 回放数据（生产接 STT 后可去掉）
COPY _archive/data ./_archive/data

ENV PORT=8080
# Cloud Run 注入 $PORT；WebSocket 长连接由 uvicorn 承载
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
