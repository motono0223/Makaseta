import { useEffect, useState } from "react";
import { api, ModelProfile } from "../api";

export default function Settings() {
  const [profiles, setProfiles] = useState<ModelProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.modelProfiles().then(setProfiles).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <>
      <h1>設定</h1>
      <section className="card">
        <h2>モデルプロファイル</h2>
        <p className="muted">
          config/models.yaml と .env の内容です。APIキーなどの秘密情報は表示しません。
        </p>
        {error && <p className="status bad">読み込みに失敗しました: {error}</p>}
        {profiles && profiles.length === 0 && <p className="muted">プロファイルがありません。</p>}
        {profiles && profiles.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>プロファイル</th>
                <th>プロバイダ</th>
                <th>モデル</th>
                <th>状態</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p) => (
                <tr key={p.name}>
                  <td>
                    <div>{p.label}</div>
                    <div className="muted small">
                      {p.name}
                      {p.is_default && " · 既定"}
                      {p.kind === "embedding" && " · 埋め込み"}
                    </div>
                  </td>
                  <td>{p.provider}</td>
                  <td className="mono small">{p.model}</td>
                  <td>
                    {p.available ? (
                      <span className="status ok">利用可能</span>
                    ) : (
                      <span className="status bad">{p.reason}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
