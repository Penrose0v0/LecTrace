# LecTrace —— 单容器（后端 API + WS + 前端静态），部署到 Cloud Run
FROM python:3.13-slim

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY frontend ./frontend
# 回放归档只在本地开发用，不进镜像（没有归档时前端自动隐藏"回放"选项）

ENV PORT=8080
# Cloud Run 注入 $PORT；WebSocket 长连接由 uvicorn 承载
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
