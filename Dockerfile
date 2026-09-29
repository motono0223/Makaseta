# ---- 画面（React）のビルド ----
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- アプリ本体（FastAPI） ----
FROM python:3.12-slim
ARG APP_UID=1000
ARG APP_GID=1000

RUN groupadd -g "${APP_GID}" app \
    && useradd -m -u "${APP_UID}" -g app app \
    && mkdir -p /data/files /library \
    && chown -R app:app /data /library

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY --from=frontend /build/dist ./static

ENV PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static

USER app
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
