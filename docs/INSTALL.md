# インストールと設定

- [必要なもの](#必要なもの)
- [インストール](#インストール)
- [LLMの設定](#llmの設定)
- [ポートの変更](#ポートの変更)
- [LAN内の他のPCから使う](#lan内の他のpcから使う)
- [資料室のフォルダ](#資料室のフォルダ)
- [.env の設定一覧](#env-の設定一覧)
- [データの保存場所とバックアップ](#データの保存場所とバックアップ)
- [アップデート](#アップデート)
- [PCの引っ越し](#pcの引っ越し)
- [困ったとき](#困ったとき)

## 必要なもの

- Docker と Docker Compose v2.24 以降（Linux / macOS / Windows + WSL2）
- 使うLLMの認証情報（どちらか）
  - Anthropic API のAPIキー（[Claude Console](https://console.anthropic.com) で発行）
  - AWS Bedrock を使える AWS アカウント（ホストで `aws configure` 済みであること）

## インストール

```bash
git clone https://github.com/motono0223/Makaseta.git
cd Makaseta
cp .env.example .env
```

`.env` を開き、少なくともLLMの認証情報を書きます（[LLMの設定](#llmの設定)）。Anthropic API なら次の1行で動きます。

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
```

起動します。

```bash
docker compose up -d --build
```

初回は、サンドボックス（LibreOffice などを含む）のビルドに数分かかります。ブラウザで http://localhost:8081 を開き、画面の「設定」で使うモデルが「利用可能」になっていれば準備完了です。

止めるときは `docker compose down` です（データは `./data` などに残ります）。

> Bedrock を使わない場合も、ホストに `~/.aws` がないと Docker が root 所有の空フォルダを作ります。気になる場合は先に `mkdir -p ~/.aws` を実行するか、`.env` の `AWS_CONFIG_DIR` で別の場所を指定してください。

## LLMの設定

1. `.env` に認証情報を書きます（使うものだけ）。
   - **Anthropic API**（Claude を直接呼ぶ）: `ANTHROPIC_API_KEY` を設定します。既定のプロファイル `claude-main` はこれを使います（モデルは Claude Haiku 4.5）。Web検索が使えるのはこちらだけです。
   - **AWS Bedrock**: ホストの `~/.aws` を読み取り専用でマウントします。場所が違う場合は `AWS_CONFIG_DIR` を設定します。`AWS_PROFILE` と `AWS_REGION` も確認してください。プロファイル `claude-bedrock` がこれを使います。
   - OpenAI / Gemini / DeepSeek: 設定欄はありますが、まだ呼び出せません（対応予定）。
2. `config/models.yaml` の `model` に、使うモデルのIDを書きます。料金の計算に使う単価（`price_per_mtok`）もここにあります。
3. 新しく雇う社員の既定のモデルは `.env` の `DEFAULT_MODEL_PROFILE` で選びます。社員ごとのモデルは社員名簿で変えられます。
4. 画面の「設定」で、各プロファイルが「利用可能」になっているか確認します。

APIキーは `.env` にだけ置き、画面やログには出しません。`.env` は Git にコミットされません。

利用料金は設定画面で確認できます。今月の料金が `MONTHLY_BUDGET_USD`（既定 50 ドル）に達すると、新しい作業を始めなくなります。

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

## LAN内の他のPCから使う

初期設定では、このPCからしかアクセスできません（`127.0.0.1` にだけ公開）。LAN や Tailscale などに公開する場合は、`.env` で次のようにします。

```dotenv
MAKASETA_BIND=0.0.0.0
MAKASETA_PASSWORD=長く推測されにくいパスワード
```

**公開するときは、必ずパスワードを設定してください。** パスワードを設定すると、画面を開いたときにログインを求めます（ログインは30日間有効です）。通信は暗号化されない（http）ので、インターネットには直接公開しないでください。

## 資料室のフォルダ

ホストの `./library` フォルダが資料室の置き場です。直下のフォルダ1つが1つの資料室になります。別の場所（例: Windows のフォルダ `/mnt/c/Users/you/Documents/makaseta`）を使う場合は、`.env` の `LIBRARY_DIR` を変更します。

資料室の使い方は [使い方ガイド](USAGE.md#資料室) を見てください。

## .env の設定一覧

| 設定 | 既定 | 内容 |
| --- | --- | --- |
| `MAKASETA_PORT` | `8081` | ブラウザで開くポート |
| `MAKASETA_BIND` | `127.0.0.1` | `0.0.0.0` にすると他のPCから開ける |
| `MAKASETA_PASSWORD` | （空） | ログインのパスワード。空ならログインなし |
| `LIBRARY_DIR` | `./library` | 資料室として使うホストのフォルダ |
| `CONFIDENTIAL_PROVIDERS` | `bedrock` | 「機密」の資料室を読めるモデルのプロバイダ（カンマ区切り） |
| `POSTGRES_PASSWORD` | `makaseta` | データベースのパスワード |
| `AWS_CONFIG_DIR` / `AWS_PROFILE` / `AWS_REGION` | `~/.aws` / `default` / `us-east-1` | Bedrock の認証情報 |
| `ANTHROPIC_API_KEY` | （空） | Anthropic API のAPIキー |
| `DEFAULT_MODEL_PROFILE` | `claude-main` | 新しい社員の既定のモデル（`config/models.yaml` のプロファイル名） |
| `MAX_CONCURRENT_RUNS` | `3` | 同時に動ける社員の作業の数 |
| `MONTHLY_BUDGET_USD` | `50` | 今月の料金がこの額（米ドル）に達したら新しい作業を止める（0で無制限） |
| `MAX_STEPS_PER_RUN` | `40` | 1回の作業で社員がモデルを呼べる回数 |
| `MAX_ACTIVE_TASKS_PER_AGENT` | `1` | マネージャーがバックログから着手させるとき、1人が同時に進めるタスクの数 |
| `AGENT_REFLECTION` | `true` | レビューのたびに社員が振り返り、業務メモを書く |
| `WEB_SEARCH_PRICE_USD` | `0.01` | Web検索1回の料金（料金の計算用） |
| `SANDBOX_OFFLINE` | `true` | `false` にするとサンドボックスがインターネットに接続できる |
| `SANDBOX_MEMORY` / `SANDBOX_CPUS` | `2g` / `2` | サンドボックスのメモリとCPUの上限 |
| `GITHUB_TOKEN` | （空） | 非公開の GitHub リポジトリからスキルを取り込む場合のトークン |

変更したら `docker compose up -d` で反映します。

## データの保存場所とバックアップ

| パス | 中身 |
| --- | --- |
| `./data/postgres` | データベース（社員、プロジェクト、タスク、会話など） |
| `./library` | 資料室のファイル（`LIBRARY_DIR` で変更可） |
| `./skills` | 導入したスキル |
| `./data/work` | タスクごとの作業フォルダ（サンドボックスと共有） |
| `./data/files` | 承認待ちのファイル成果物、引っ越し用の書き出し |

バックアップは、`docker compose down` で止めてから `./data`・`./library`・`./skills`・`.env` をコピーするだけです。

## アップデート

```bash
git pull
docker compose up -d --build
```

データベースの更新は起動時に自動で行われます。念のため、先に[バックアップ](#データの保存場所とバックアップ)を取ってください。

## PCの引っ越し

設定画面の「オフィスの引っ越し」で、社員（業務メモを含む）・プロジェクト・会話・資料室・スキル・承認待ちのファイルを1つの zip に書き出せます。

1. 元のPCで「書き出す」を押し、zip をダウンロードします。
2. 新しいPCで makaseta を[インストール](#インストール)し（同じバージョン）、`.env` を設定します。zip には `.env`（APIキーやパスワード）は含まれません。
3. 新しいPCの設定画面で「書き出したファイルを取り込む」を選びます。取り込み先の内容は置き換わり、取り込む前の状態は自動でバックアップされます。

`config/models.yaml` は zip に参考として入っています。モデルの設定を変えていた場合は、新しいPCの `config/` にコピーしてください。

## 困ったとき

- **画面が開けない**: `docker compose ps` で `app` が動いているか、`docker compose logs app` でエラーが出ていないか確認します。ポートがほかのアプリと重なっている場合は [ポートを変更](#ポートの変更) します。
- **他のPCから開けない**: `MAKASETA_BIND=0.0.0.0` になっているか、ホストのファイアウォールを確認します。WSL2 の場合は、Windows 側からの転送（ミラーモードなど）も必要です。
- **モデルが「利用可能」にならない**: `.env` のAPIキーや `~/.aws` の設定を確認し、`docker compose up -d` をやり直します。
- **社員が作業を始めない**: 設定画面で今月の利用料金が上限に達していないか確認します。
