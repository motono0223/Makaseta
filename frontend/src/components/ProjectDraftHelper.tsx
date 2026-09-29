import { useState } from "react";
import { Agent, AgentTemplate, ModelProfile, ProjectDraft, ProjectRole, Skill, api } from "../api";

type NewMember = ProjectDraft["new_members"][number];

type Props = {
  agents: Agent[];
  roles: ProjectRole[];
  onDraft: (draft: ProjectDraft) => void;
  onHired: (agent: Agent, roleId: number) => void;
};

/** Turn a one-line idea into a project draft and a team, and hire the members that are missing. */
export default function ProjectDraftHelper({ agents, roles, onDraft, onHired }: Props) {
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<ProjectDraft | null>(null);
  const [hired, setHired] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const agentName = (id: number | null) => agents.find((a) => a.id === id)?.name ?? "";
  const roleName = (id: number) => roles.find((r) => r.id === id)?.name ?? "";

  async function makeDraft() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.projectDraft(idea);
      setDraft(result);
      setHired([]);
      onDraft(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function hire(member: NewMember) {
    setBusy(true);
    setError(null);
    try {
      let agent: Agent;
      if (member.clone_of) {
        agent = await api.cloneAgent(member.clone_of, member.name, true);
      } else {
        const [templates, skills, profiles]: [AgentTemplate[], Skill[], ModelProfile[]] = await Promise.all([
          api.agentTemplates(), api.skills(), api.modelProfiles(),
        ]);
        const t = templates.find((x) => x.key === member.template_key);
        const profile = profiles.find((p) => p.is_default && p.kind === "chat") ?? profiles.find((p) => p.kind === "chat");
        agent = await api.hireAgent({
          name: member.name,
          title: t?.title ?? member.title,
          avatar_color: t?.avatar_color ?? "c1",
          personality: t?.personality ?? "",
          instructions: t?.instructions ?? "",
          model_profile: profile?.name ?? "",
          skill_ids: skills.filter((s) => s.key && t?.skill_keys.includes(s.key)).map((s) => s.id),
          template_key: t?.key ?? null,
        });
      }
      setHired((h) => [...h, member.name]);
      onHired(agent, member.role_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card draft-helper">
      <h2>✨ やりたいことから下書きを作る</h2>
      <div className="inline-form">
        <input value={idea} onChange={(e) => setIdea(e.target.value)} maxLength={2000}
          placeholder="例: 4月入社の新人向けに、社内規程をわかりやすく説明する研修資料を作りたい" aria-label="やりたいこと"
          onKeyDown={(e) => {
            if (e.key === "Enter" && idea.trim()) {
              e.preventDefault();
              makeDraft();
            }
          }} />
        <button type="button" className="btn primary" disabled={busy || !idea.trim()} onClick={makeDraft}>
          {busy && !draft ? "考えています…" : "下書きを作る"}
        </button>
      </div>
      <p className="muted small">名前・目的・完了条件を下書きし、今いる社員からメンバーとロールを提案します。下の欄はあとから自由に直せます。</p>
      {error && <p className="status bad">{error}</p>}
      {draft && (
        <div className="draft-result">
          {draft.members.length > 0 && (
            <ul className="small">
              {draft.members.map((m) => (
                <li key={m.agent_id}>
                  <strong>{agentName(m.agent_id)}</strong>（{roleName(m.role_id)}{m.is_primary && "・窓口"}）
                  <span className="muted"> {m.reason}</span>
                </li>
              ))}
            </ul>
          )}
          {draft.new_members.length > 0 && (
            <div className="new-members">
              <div className="small"><strong>足りない役割（新しく雇う提案）</strong></div>
              {draft.new_members.map((m) => (
                <div key={m.name} className="member-row">
                  <div className="grow small">
                    <strong>{m.name}</strong>（{m.title}・{roleName(m.role_id)}）
                    {m.clone_of && <span className="muted"> {agentName(m.clone_of)}さんを複製（業務メモも引き継ぐ）</span>}
                    <div className="muted">{m.reason}</div>
                  </div>
                  {hired.includes(m.name) ? (
                    <span className="status ok small">雇ってメンバーに加えました</span>
                  ) : (
                    <button type="button" className="btn small-btn" disabled={busy} onClick={() => hire(m)}>
                      雇ってメンバーに加える
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {draft.rooms.length > 0 && (
            <p className="small muted">
              資料室: {draft.rooms.map((r) => `${r.room}（${r.access === "write" ? "読み書き" : "読み取り"}）`).join("、")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
