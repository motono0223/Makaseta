import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Agent, ModelProfile, api } from "../api";
import Avatar from "../components/Avatar";
import StatusBadge from "../components/StatusBadge";

export default function Staff() {
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [showRetired, setShowRetired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.agents(showRetired).then(setAgents).catch((e: Error) => setError(e.message));
  }, [showRetired]);

  useEffect(() => {
    api.modelProfiles().then(setProfiles).catch(() => undefined);
  }, []);

  const profileLabel = (name: string) => profiles.find((p) => p.name === name)?.label ?? name;

  return (
    <>
      <div className="page-header">
        <div>
          <h1>社員名簿</h1>
          <p className="lead">雇っている社員の一覧です。社員をクリックすると詳細を開きます。</p>
        </div>
        <Link to="/staff/new" className="btn primary">
          社員を雇う
        </Link>
      </div>

      <label className="toggle">
        <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} />
        退職した社員も表示
      </label>

      {error && <p className="status bad">読み込みに失敗しました: {error}</p>}
      {agents && agents.length === 0 && (
        <section className="card empty">
          <p>まだ社員がいません。</p>
          <Link to="/staff/new" className="btn primary">
            最初の社員を雇う
          </Link>
        </section>
      )}

      <div className="agent-grid">
        {agents?.map((a) => (
          <Link key={a.id} to={`/staff/${a.id}`} className={`agent-card${a.active ? "" : " retired"}`}>
            <div className="agent-card-head">
              <Avatar name={a.name} color={a.avatar_color} />
              <div className="grow">
                <div className="agent-name">{a.name}</div>
                <div className="muted small">{a.title || "役職なし"}</div>
              </div>
              <StatusBadge agent={a} />
            </div>
            <div className="muted small">モデル: {profileLabel(a.model_profile)}</div>
            <div className="chips">
              {a.skills.length === 0 && <span className="muted small">スキルなし</span>}
              {a.skills.map((s) => (
                <span key={s.id} className="chip">
                  {s.name}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
