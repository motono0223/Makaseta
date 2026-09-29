import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Project, api } from "../api";
import Avatar from "../components/Avatar";
import { PROJECT_STATUS, TASK_COLUMNS } from "../labels";

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects(showArchived).then(setProjects).catch((e: Error) => setError(e.message));
  }, [showArchived]);

  return (
    <>
      <div className="page-header">
        <div>
          <h1>プロジェクト</h1>
          <p className="lead">プロジェクトごとに社員をアサインし、バックログのタスクを任せます。</p>
        </div>
        <Link to="/projects/new" className="btn primary">プロジェクトを立ち上げる</Link>
      </div>

      <label className="toggle">
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
        アーカイブしたプロジェクトも表示
      </label>

      {error && <p className="status bad">{error}</p>}
      {projects && projects.length === 0 && (
        <section className="card empty">
          <p>まだプロジェクトがありません。</p>
          <Link to="/projects/new" className="btn primary">最初のプロジェクトを立ち上げる</Link>
        </section>
      )}

      <div className="agent-grid">
        {projects?.map((p) => {
          const total = Object.values(p.task_counts).reduce((a, b) => a + (b ?? 0), 0);
          const done = p.task_counts.done ?? 0;
          const primary = p.members.find((m) => m.is_primary);
          return (
            <Link key={p.id} to={`/projects/${p.id}`} className="agent-card">
              <div className="agent-card-head">
                <div className="grow">
                  <div className="agent-name">{p.name}</div>
                  <div className="muted small">{p.goal || "目的未設定"}</div>
                </div>
                <span className={`badge project-${p.status}`}>{PROJECT_STATUS[p.status]}</span>
              </div>
              <div className="avatar-stack">
                {p.members.map((m) => (
                  <span key={m.agent.id} title={`${m.agent.name}（${m.role.name}）`}>
                    <Avatar name={m.agent.name} color={m.agent.avatar_color} size={28} />
                  </span>
                ))}
                {primary && <span className="muted small">窓口: {primary.agent.name}</span>}
              </div>
              <div className="progress" aria-label={`完了 ${done}/${total}`}>
                <div className="progress-bar" style={{ width: total ? `${(done / total) * 100}%` : 0 }} />
              </div>
              <div className="muted small">
                {TASK_COLUMNS.filter((c) => p.task_counts[c.status]).map((c) => `${c.label} ${p.task_counts[c.status]}`)
                  .join(" · ") || "タスクなし"}
                {p.due_date && ` · 期限 ${p.due_date}`}
              </div>
            </Link>
          );
        })}
      </div>
    </>
  );
}
