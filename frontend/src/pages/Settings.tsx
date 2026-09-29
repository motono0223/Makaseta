import { useEffect, useState } from "react";
import { api, ModelProfile, UsageSummary, UsageRow } from "../api";

export default function Settings() {
  const [profiles, setProfiles] = useState<ModelProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);

  useEffect(() => {
    api.modelProfiles().then(setProfiles).catch((e: Error) => setError(e.message));
    api.usage().then(setUsage).catch(() => undefined);
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

      {usage && (
        <section className="card">
          <h2>今月の利用料金（概算）</h2>
          <p>
            <strong>${Number(usage.month_spend_usd).toFixed(4)}</strong>
            <span className="muted"> / 予算 ${usage.monthly_budget_usd.toFixed(2)}（.env の MONTHLY_BUDGET_USD）</span>
          </p>
          <div className="progress">
            <div className="progress-bar" style={{
              width: `${Math.min((Number(usage.month_spend_usd) / (usage.monthly_budget_usd || 1)) * 100, 100)}%`,
            }} />
          </div>
          <div className="usage-grid">
            <UsageTable title="社員別" rows={usage.by_agent} />
            <UsageTable title="プロジェクト別" rows={usage.by_project} />
          </div>
          <p className="muted small">料金は config/models.yaml の price_per_mtok から計算した目安です。</p>
        </section>
      )}
    </>
  );
}

function UsageTable({ title, rows }: { title: string; rows: UsageRow[] }) {
  return (
    <div>
      <h3>{title}</h3>
      <table className="table">
        <tbody>
          {rows.map((r) => (
            <tr key={String(r.id)}>
              <td>{r.name}</td>
              <td className="num">${r.cost_usd.toFixed(4)}</td>
              <td className="num muted small">{(r.input_tokens + r.output_tokens).toLocaleString()} tok</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="muted">まだ利用はありません</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
