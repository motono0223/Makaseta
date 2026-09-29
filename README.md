# makaseta（任せた）

AI社員に仕事を任せる、あなただけの仮想オフィス。

あなたはオフィス長です。LLMで動く「社員」を雇い、プロジェクトを立ち上げてアサインし、バックログのタスクを任せて、成果物を承認します。
社員はプロジェクトにリンクされた「資料室」（共有の文書置き場）の資料を読み、成果物を資料室に保存します。

> **English:** makaseta ("I'll leave it to you" in Japanese) is a self-hosted virtual office where you manage LLM agents as employees: hire them, assign them to project backlogs, and review their deliverables. Runs locally with Docker; supports Claude (Anthropic API or AWS Bedrock), OpenAI, Gemini and DeepSeek.

> 開発中です（フェーズ1: MVP）。社員の雇用、資料室、プロジェクトとカンバン、社員が資料を調べて成果物を提出する仕組み、社員スレッドまで動きます。

## 特長

- **社員（AIエージェント）を雇う**: 役職、性格、スキル、使うモデルを設定
- **プロジェクトとバックログ**: タスクはプロジェクトに積み、社員をアサインして消化
- **マネージャー社員が窓口**: 依頼を分解して社員に割り振り、取りまとめる
- **資料室**: 手元のフォルダがそのまま文書置き場になる。プロジェクトごとに読み取り専用／読み書きでリンク
- **ローカルで完結**: Docker Composeで起動し、データはすべて手元の `./data` に保存
- **LLMを選べる**: Anthropic API・AWS Bedrock（Claude）、OpenAI、Gemini、DeepSeek

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

初回は、サンドボックス（LibreOffice などを含む）のビルドに数分かかります。

ブラウザで http://localhost:8081 を開きます。

> Bedrockを使わない場合も、ホストに `~/.aws` がないとDockerがroot所有の空フォルダを作ります。気になる場合は先に `mkdir -p ~/.aws` を実行するか、`.env` の `AWS_CONFIG_DIR` で別の場所を指定してください。

止めるときは `docker compose down` です（データは `./data` に残ります）。

## 使い方の流れ

1. **社員を雇う**（社員名簿）: 役職を選ぶと性格とスキルの初期値が入ります。使うモデルもここで選びます。
2. **資料を置く**（資料室）: 社員に読ませたい資料をフォルダにコピーします。
3. **プロジェクトを立ち上げる**: メンバーとロール（マネージャーは1人以上）、読ませる資料室を決めます。成果物を保存させたい資料室は「読み書き」にします。
4. **タスクを任せる**: カンバンでタスクを作り、担当を決めて「作業中」に移すと、社員が作業を始めます。
   - 社員は資料室を検索して読み、成果物を提出し、終わると報告します（タスクは「レビュー待ち」へ）。
   - 情報が足りないと質問してきます（「質問待ち」）。受信箱かスレッドから回答すると再開します。
5. **レビューする**: 成果物を確認して「承認」すると資料室に保存され、タスクは完了します（同名のファイルがあれば、旧版を資料室の `.makaseta/versions` に残してから上書きします）。「差し戻す」と、コメントを踏まえて社員がやり直します。
6. **マネージャーに任せる**: プロジェクトの「スレッド」から窓口のマネージャーに依頼すると、マネージャーがメンバーに割り振った計画を提案します。承認すると、前後関係どおりにタスクが自動で進み、最後にマネージャーが取りまとめて報告します。
7. **社員と話す**: 社員のアイコンをクリックするとスレッドが開きます。進捗を聞いたり、作業中の社員に追加の指示を出したりできます。

作業ログ（社員が何を調べ、何を考えたか）と利用料金は、タスクの「作業」タブと設定画面で確認できます。

## スキル（Agent Skills）

社員には、[Agent Skills](https://github.com/anthropics/skills) 形式のスキル（`SKILL.md` とスクリプトのフォルダ）を付けられます。

1. 画面の「スキル」で、GitHub のスキルのフォルダのURL（例: `https://github.com/anthropics/skills/tree/main/skills/pptx`）を入力し、「内容を確認」を押します。
2. 手順書・ライセンス・スクリプトを確認してから「導入する」を押します（`./skills/<名前>` に保存されます）。ホストの `./skills` にフォルダを直接コピーしても追加できます。
3. 社員名簿で、社員にスキルを付けます。

社員はスキルの手順書を読み、スクリプトを **サンドボックス**（`sandbox` コンテナ）で実行して、.pptx などのファイルを成果物として提出します。

サンドボックスの安全対策:

- アプリとは別のコンテナで、一般ユーザーとして動きます。DBの接続情報やAPIキーは渡しません。
- 触れられるのは、タスクごとの作業フォルダ（`./data/work`）と、読み取り専用のスキル（`./skills`）だけです。資料室のファイルは、社員がツールでコピーしたものだけが届きます。
- 既定ではインターネットに接続できません（`.env` の `SANDBOX_OFFLINE=false` で接続可）。アプリのAPIも呼べません。
- メモリ・CPU・プロセス数に上限があり（`SANDBOX_MEMORY` / `SANDBOX_CPUS`）、コマンドは時間切れで止まります。
- Python（python-pptx・openpyxl・python-docx・pypdf・pandas・markitdown など）、uv、Node.js（pptxgenjs など）、LibreOffice、日本語フォントが入っています。

公開されているスキルは任意のコードを含みます。信頼できる提供元のスキルだけを導入してください。

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

あわせて、ログインのパスワードを必ず設定してください。

```dotenv
MAKASETA_PASSWORD=長く推測されにくいパスワード
```

パスワードを設定すると、画面を開いたときにログインを求めます（ログインは30日間有効です）。

## LLMの設定

1. `.env` に認証情報を書きます（使うものだけ）。
   - Bedrock: ホストの `~/.aws` を読み取り専用でマウントします。場所が違う場合は `AWS_CONFIG_DIR` を設定します。`AWS_PROFILE` と `AWS_REGION` も確認してください。
   - Anthropic API（Claudeを直接呼ぶ）: `ANTHROPIC_API_KEY` を設定します。既定のプロファイル `claude-main` はこれを使います（モデルは Claude Haiku 4.5）。
   - OpenAI / Gemini / DeepSeek: `OPENAI_API_KEY` などを設定します。
2. `config/models.yaml` の `model` に、使うモデルのIDを書きます。
3. 画面の「設定」で、各プロファイルが「利用可能」になっているか確認します。

APIキーは `.env` にだけ置き、画面やログには出しません。`.env` はGitにコミットされません。

## 資料室（社員が読む資料の置き場）

ホストの `./library` フォルダが資料室の置き場です。直下のフォルダ1つが1つの資料室になります。

```
library/
├── 社内規程/          ← 資料室「社内規程」
│   ├── 出張規程.md
│   └── 人事/経費精算.pdf
└── 営業資料/          ← 資料室「営業資料」
```

- エクスプローラーや `cp` でファイルを置けば、30秒以内に自動で取り込まれます（画面の「再読み込み」ですぐ反映もできます）。
- 画面からも、資料室やフォルダの作成、アップロード、Markdownメモの作成と編集、削除ができます。
- Markdown・テキスト・CSV・PDF・Word・Excel・PowerPoint からテキストを取り出し、日本語で全文検索できます。Shift_JIS のテキストも読めます。
- 名前が `.` で始まるファイルとフォルダは無視されます。
- 別の場所（例: Windows のフォルダ `/mnt/c/Users/you/Documents/makaseta`）を使う場合は、`.env` の `LIBRARY_DIR` を変更します。

## データの保存場所

| パス | 中身 |
| --- | --- |
| `./data/postgres` | データベース（社員、プロジェクト、タスク、会話など） |
| `./library` | 資料室のファイル（`LIBRARY_DIR` で変更可） |
| `./skills` | 導入したスキル |
| `./data/work` | タスクごとの作業フォルダ（サンドボックスと共有） |
| `./data/files` | 承認待ちのファイル成果物 |

バックアップは、コンテナを止めてから `./data`・`./library`・`./skills` をコピーするだけです。

## 開発

```
backend/    FastAPI（Python 3.12）
frontend/   React + TypeScript（Vite）
sandbox/    スキルを実行するサンドボックス
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
