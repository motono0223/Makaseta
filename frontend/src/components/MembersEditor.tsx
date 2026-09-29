import { Agent, MemberInput, ProjectRole } from "../api";
import Avatar from "./Avatar";

/** The project role that fits each hiring template, used as the default when adding a member. */
const ROLE_FOR_TEMPLATE: Record<string, string> = {
  manager: "manager",
  researcher: "researcher",
  analyst: "researcher",
  writer: "writer",
  reviewer: "reviewer",
};

type Props = {
  agents: Agent[];
  roles: ProjectRole[];
  value: MemberInput[];
  onChange: (members: MemberInput[]) => void;
};

/** Pick agents and their project roles. Exactly one manager is marked as the office head's contact. */
export default function MembersEditor({ agents, roles, value, onChange }: Props) {
  const roleById = new Map(roles.map((r) => [r.id, r]));
  const isManager = (m: MemberInput) => roleById.get(m.role_id)?.is_manager ?? false;
  const unused = agents.filter((a) => a.active && !value.some((m) => m.agent_id === a.id));
  const defaultRole = roles.find((r) => !r.is_manager) ?? roles[0];

  function update(next: MemberInput[]) {
    // Keep exactly one primary manager whenever there is a manager.
    const managers = next.filter(isManager);
    const hasPrimary = managers.some((m) => m.is_primary);
    onChange(
      next.map((m) => ({
        ...m,
        is_primary: isManager(m) && (hasPrimary ? m.is_primary : m.agent_id === managers[0]?.agent_id),
      })),
    );
  }

  const setRole = (agentId: number, roleId: number) =>
    update(value.map((m) => (m.agent_id === agentId ? { ...m, role_id: roleId, is_primary: false } : m)));
  const setPrimary = (agentId: number) => update(value.map((m) => ({ ...m, is_primary: m.agent_id === agentId })));
  const remove = (agentId: number) => update(value.filter((m) => m.agent_id !== agentId));
  const add = (agentId: number) => {
    const agent = agents.find((a) => a.id === agentId);
    const suggested = roles.find((r) => r.key === ROLE_FOR_TEMPLATE[agent?.template_key ?? ""]);
    const manager = roles.find((r) => r.is_manager);
    // Until someone is a manager, the next member added takes that role.
    const role = !value.some(isManager) && manager ? manager : suggested ?? defaultRole;
    update([...value, { agent_id: agentId, role_id: role.id, is_primary: false }]);
  };

  return (
    <div className="members-editor">
      {value.length === 0 && <p className="muted small">まだメンバーがいません。役職に合ったロールが選ばれます。マネージャーがまだいなければ、最初の社員がマネージャーになります。</p>}
      {value.map((m) => {
        const agent = agents.find((a) => a.id === m.agent_id);
        if (!agent) return null;
        return (
          <div key={m.agent_id} className="member-row">
            <Avatar name={agent.name} color={agent.avatar_color} size={32} />
            <div className="grow">
              <div className="agent-name">{agent.name}</div>
              <div className="muted small">{agent.title}</div>
            </div>
            <select value={m.role_id} onChange={(e) => setRole(m.agent_id, Number(e.target.value))} aria-label={`${agent.name}のロール`}>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
            <label className={`primary-toggle${isManager(m) ? "" : " hidden"}`} title="オフィス長からの依頼を受ける窓口">
              <input type="radio" name="primary-manager" checked={m.is_primary} onChange={() => setPrimary(m.agent_id)}
                disabled={!isManager(m)} />
              窓口
            </label>
            <button type="button" className="link-button danger small" onClick={() => remove(m.agent_id)}>外す</button>
          </div>
        );
      })}
      {unused.length > 0 && (
        <select className="add-member" value="" onChange={(e) => e.target.value && add(Number(e.target.value))}
          aria-label="メンバーを追加">
          <option value="">＋ 社員を追加…</option>
          {unused.map((a) => (
            <option key={a.id} value={a.id}>{a.name}（{a.title || "役職なし"}）</option>
          ))}
        </select>
      )}
      {agents.filter((a) => a.active).length === 0 && (
        <p className="hint warn">まだ社員がいません。先に社員名簿で社員を雇ってください。</p>
      )}
      {value.length > 0 && !value.some(isManager) && <p className="hint warn">マネージャーを1人以上選んでください。</p>}
    </div>
  );
}
