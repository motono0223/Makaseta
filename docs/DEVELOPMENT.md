# 開発

## 構成

```
backend/    FastAPI（Python 3.12）。migrations/ はデータベースの更新（Alembic、起動時に自動実行）
frontend/   React + TypeScript（Vite）。ビルドした画面は app コンテナから配信
sandbox/    スキルのスクリプトを実行するサンドボックス
config/     モデルプロファイル（models.yaml）
docs/       ドキュメント
```

`docker compose` で次の3つのコンテナが動きます。

| コンテナ | 役割 |
| --- | --- |
| `app` | API と画面。社員の作業（LLMの呼び出しとツール）もここで動く |
| `db` | PostgreSQL（pgvector） |
| `sandbox` | スキルのスクリプトを実行する。アプリとは別の、インターネットにつながらないネットワークにいる |

## 画面をホットリロードで開発する

Node.js 20 以降が必要です。ローカルからDBに接続するため、`docker-compose.yml` の `db` に `ports: ["127.0.0.1:5432:5432"]` を追加してから始めます。

```bash
docker compose up -d db
cd backend && pip install -r requirements.txt \
  && DATABASE_URL=postgresql+psycopg://makaseta:makaseta@localhost:5432/makaseta uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## 変更をコンテナに反映する

```bash
docker compose up -d --build app
```
