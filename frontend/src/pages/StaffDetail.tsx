import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Agent, AgentInput, Assignment, api } from "../api";
import AgentForm from "../components/AgentForm";
import Avatar from "../components/Avatar";
import StatusBadge from "../components/StatusBadge";
import { useThread } from "../components/ThreadDrawer";
import { PRIORITY, PROJECT_STATUS, TASK_STATUS } from "../labels";

export default function StaffDetail() {
  const { id } = useParams();
  const agentId = Number(id);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const openThread = useThread();

  useEffect(() => {
    api.agent(agentId).then(setAgent).catch((e: Error) => setError(e.message));
    api.assignments(agentId).then(setAssignments).catch(() => undefined);
  }, [agentId]);

  const initial = useMemo<AgentInput | null>(
    () =>
      agent && {
        name: agent.name,
        title: agent.title,
        avatar_color: agent.avatar_color,
        personality: agent.personality,
        instructions: agent.instructions,
        model_profile: agent.model_profile,
        skill_ids: agent.skills.map((s) => s.id),
      },
    [agent],
  );

  async function save(values: AgentInput) {
    const updated = await api.updateAgent(agentId, values);
    setAgent(updated);
    setNotice("保存しました");
  }

  async function toggleEmployment() {
    if (!agent) return;
    setError(null);
    setNotice(null);
    if (agent.active && !window.confirm(`${agent.name}さんを退職させますか？これまでの作業記録は残ります。`)) return;
    try {
      setAgent(agent.active ? await api.retireAgent(agentId) : await api.rehireAgent(agentId));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (error && !agent) return <p className="status bad">{error}</p>;
  if (!agent || !initial) return <p className="muted">読み込み中…</p>;

  return (
    <>
      <p className="breadcrumb">
        <Link to="/staff">社員名簿</Link> / {agent.name}
      </p>
      <div className="page-header">
        <div className="agent-card-head">
          <Avatar name={agent.name} color={agent.avatar_color} size={56} />
          <div>
            <h1>{agent.name}</h1>
            <div className="muted">{agent.title || "役職なし"}</div>
          </div>
          <StatusBadge agent={agent} />
        </div>
        <div className="header-actions">
          {agent.active && <button type="button" className="btn primary" onClick={() => openThread(agent.id)}>💬 スレッドを開く</button>}
          <button type="button" className={agent.active ? "btn danger" : "btn"} onClick={toggleEmployment}>
            {agent.active ? "退職させる" : "再雇用する"}
          </button>
        </div>
      </div>

      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}

      <section className="card">
        <h2>プロフィール</h2>
        <AgentForm initial={initial} submitLabel="保存する" onSubmit={save} />
      </section>

      <section className="card">
        <h2>所属プロジェクトと担当タスク</h2>
        {assignments.length === 0 && <p className="muted">まだどのプロジェクトにもアサインされていません。</p>}
        {assignments.map((a) => (
          <div key={a.project_id} className="assignment">
            <div className="assignment-head">
              <Link to={`/projects/${a.project_id}`} className="agent-name">{a.project_name}</Link>
              <span className="muted small">{a.role.name}{a.is_primary && "・窓口"} · {PROJECT_STATUS[a.project_status]}</span>
            </div>
            {a.tasks.length === 0 ? (
              <p className="muted small">担当タスクはありません。</p>
            ) : (
              <ul className="task-list">
                {a.tasks.map((t) => (
                  <li key={t.id}>
                    <span className={`badge task-${t.status}`}>{TASK_STATUS[t.status]}</span>{" "}
                    <Link to={`/projects/${a.project_id}?task=${t.id}`}>{t.title}</Link>
                    {t.priority !== "normal" && <span className="muted small"> · 優先度 {PRIORITY[t.priority]}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </section>
    </>
  );
}
