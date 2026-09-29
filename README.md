# makaseta（任せた）

AI社員に仕事を任せる、あなただけの仮想オフィス。

あなたはオフィス長です。LLMで動く「社員」を雇い、プロジェクトを立ち上げてアサインし、バックログのタスクを任せて、成果物を承認します。
社員はプロジェクトにリンクされた「バケット」（共有の文書置き場）の資料を読み、成果物をバケットに保存します。

> **English:** makaseta ("I'll leave it to you" in Japanese) is a self-hosted virtual office where you manage LLM agents as employees: hire them, assign them to project backlogs, and review their deliverables. Runs locally with Docker; supports AWS Bedrock (Claude), OpenAI, Gemini and DeepSeek.

> 開発中です（フェーズ1: MVP）。現在は起動と設定確認の画面までできています。

## 特長

- **社員（AIエージェント）を雇う**: 役職、性格、スキル、使うモデルを設定
- **プロジェクトとバックログ**: タスクはプロジェクトに積み、社員をアサインして消化
- **マネージャー社員が窓口**: 依頼を分解して社員に割り振り、取りまとめる
- **バケット**: SharePointのような文書置き場。プロジェクトごとに読み取り専用／読み書きでリンク
- **ローカルで完結**: Docker Composeで起動し、データはすべて手元の `./data` に保存
- **LLMを選べる**: AWS Bedrock（Claude）、OpenAI、Gemini、DeepSeek

## 必要なもの

- Docker と Docker Compose v2.24 以降（Linux / macOS / Windows + WSL2）
- 使うLLMの認証情報（Bedrockならホストで `aws configure` 済みであること）

## はじめかた

```bash
git clone https://github.com/motono0223/Makaseta.git
cd Makaseta
cp .env.example .env        # 必要に応じて編集
docker compose up -d --build
```

ブラウザで http://localhost:8081 を開きます。

> Bedrockを使わない場合も、ホストに `~/.aws` がないとDockerがroot所有の空フォルダを作ります。気になる場合は先に `mkdir -p ~/.aws` を実行するか、`.env` の `AWS_CONFIG_DIR` で別の場所を指定してください。

止めるときは `docker compose down` です（データは `./data` に残ります）。

## ポートの変更

`.env` の `MAKASETA_PORT` を変えます。

```dotenv
MAKASETA_PORT=3000
```

`docker compose up -d` をやり直すと http://localhost:3000 で開けます。一時的に変えるだけなら、次のようにも起動できます。

```bash
MAKASETA_PORT=3000 docker compose up -d
```

`docker-compose.yml` の `ports` を直接書き換えても構いません。コンテナ内のアプリは常に 8080 で待ち受けるので、右側の `8080` は変えないでください。

### LAN内の他のPCから使う

初期設定では、このPCからしかアクセスできません（`127.0.0.1` にだけ公開）。LANに公開する場合は `.env` で次のようにします。

```dotenv
MAKASETA_BIND=0.0.0.0
```

> 現時点ではログイン機能がありません。LANに公開するのは、信頼できるネットワークの中だけにしてください。

## LLMの設定

1. `.env` に認証情報を書きます（使うものだけ）。
   - Bedrock: ホストの `~/.aws` を読み取り専用でマウントします。場所が違う場合は `AWS_CONFIG_DIR` を設定します。`AWS_PROFILE` と `AWS_REGION` も確認してください。
   - OpenAI / Gemini / DeepSeek: `OPENAI_API_KEY` などを設定します。
2. `config/models.yaml` の `model` に、使うモデルのIDを書きます。
3. 画面の「設定」で、各プロファイルが「利用可能」になっているか確認します。

APIキーは `.env` にだけ置き、画面やログには出しません。`.env` はGitにコミットされません。

## データの保存場所

| パス | 中身 |
| --- | --- |
| `./data/postgres` | データベース（社員、プロジェクト、タスク、会話など） |
| `./data/files` | バケットの文書ファイル |

バックアップは、コンテナを止めてから `./data` をコピーするだけです。

## 開発

```
backend/    FastAPI（Python 3.12）
frontend/   React + TypeScript（Vite）
config/     モデルプロファイル
```

画面をホットリロードで開発する場合（Node.js 20以降が必要）:

```bash
docker compose up -d db
cd backend && pip install -r requirements.txt \
  && DATABASE_URL=postgresql+psycopg://makaseta:makaseta@localhost:5432/makaseta uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

※ ローカルからDBに接続するには、`docker-compose.yml` の `db` に `ports: ["127.0.0.1:5432:5432"]` を追加してください。

## ライセンス

[MIT](LICENSE)
