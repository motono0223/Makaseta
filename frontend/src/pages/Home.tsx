import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Health, InboxItem, UsageSummary } from "../api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inbox, setInbox] = useState<InboxItem[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message));
    api.inbox().then(setInbox).catch(() => undefined);
    api.usage().then(setUsage).catch(() => undefined);
  }, []);

  const count = (kind: InboxItem["kind"]) => inbox.filter((i) => i.kind === kind).length;

  return (
    <>
      <h1>オフィスホーム</h1>
      <p className="lead">ようこそ、オフィス長。社員を雇い、プロジェクトを立ち上げて、仕事を任せましょう。</p>

      <div className="stat-row">
        <Link to="/inbox" className="stat">
          <span className="stat-value">{count("question")}</span>
          <span className="stat-label">回答待ちの質問</span>
        </Link>
        <Link to="/inbox" className="stat">
          <span className="stat-value">{count("review")}</span>
          <span className="stat-label">レビュー待ち</span>
        </Link>
        <Link to="/inbox" className="stat">
          <span className="stat-value">{count("failed")}</span>
          <span className="stat-label">止まった作業</span>
        </Link>
        <Link to="/settings" className="stat">
          <span className="stat-value">${usage ? Number(usage.month_spend_usd).toFixed(2) : "–"}</span>
          <span className="stat-label">今月の利用料金</span>
        </Link>
      </div>

      <section className="card">
        <h2>システムの状態</h2>
        {error && <p className="status bad">APIに接続できません: {error}</p>}
        {!health && !error && <p className="muted">確認中…</p>}
        {health && (
          <ul className="status-list">
            <li className={health.database.ok ? "status ok" : "status bad"}>
              データベース: {health.database.ok ? "接続OK" : "接続エラー"}（{health.database.detail}）
            </li>
            <li className={health.storage.ok ? "status ok" : "status bad"}>
              資料室のフォルダ: {health.storage.ok ? "OK" : "見つかりません"}（{health.storage.path}）
            </li>
            <li className={health.sandbox.ok ? "status ok" : "status bad"}>
              サンドボックス（スキルの実行環境）: {health.sandbox.ok ? "OK" : "停止中（スキルのスクリプトは実行できません）"}
            </li>
            <li className="muted">バージョン {health.version}</li>
          </ul>
        )}
      </section>

      <section className="card">
        <h2>はじめに</h2>
        <ol>
          <li>設定画面で、使えるLLMモデルを確認する</li>
          <li>社員名簿で社員を雇う（マネージャーを1人以上）</li>
          <li>資料室に資料を置く</li>
          <li>プロジェクトを立ち上げ、メンバーと資料室を決める</li>
          <li>カンバンにカードを置くか、プロジェクトのスレッドでマネージャーに依頼する</li>
        </ol>
        <p className="muted">
          担当者のいないカードはマネージャーが割り振り、大きな仕事はサブタスクに分けます。社員からの質問と成果物は受信箱に届きます。
          社員のアイコンをクリックすると、スレッドで話せます。
        </p>
      </section>
    </>
  );
}
