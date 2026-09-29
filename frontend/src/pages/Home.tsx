import { useEffect, useState } from "react";
import { api, Health } from "../api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <>
      <h1>オフィスホーム</h1>
      <p className="lead">ようこそ、オフィス長。社員を雇い、プロジェクトを立ち上げて、仕事を任せましょう。</p>

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
            <li className="muted">バージョン {health.version}</li>
          </ul>
        )}
      </section>

      <section className="card">
        <h2>はじめに</h2>
        <ol>
          <li>設定画面で、使えるLLMモデルを確認する</li>
          <li>社員名簿で社員を雇う</li>
          <li>プロジェクトを立ち上げ、マネージャー社員をアサインする</li>
        </ol>
        <p className="muted">プロジェクト・資料室はフェーズ1で順に実装します。</p>
      </section>
    </>
  );
}
