import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Agent, AgentInput, api } from "../api";
import AgentForm from "../components/AgentForm";
import Avatar from "../components/Avatar";
import StatusBadge from "../components/StatusBadge";

export default function StaffDetail() {
  const { id } = useParams();
  const agentId = Number(id);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    api.agent(agentId).then(setAgent).catch((e: Error) => setError(e.message));
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
        <button type="button" className={agent.active ? "btn danger" : "btn"} onClick={toggleEmployment}>
          {agent.active ? "退職させる" : "再雇用する"}
        </button>
      </div>

      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}

      <section className="card">
        <h2>プロフィール</h2>
        <AgentForm initial={initial} submitLabel="保存する" onSubmit={save} />
      </section>

      <section className="card">
        <h2>担当タスクと会話</h2>
        <p className="muted">プロジェクト機能ができると、ここに担当タスクと社員スレッドが表示されます。</p>
      </section>
    </>
  );
}
