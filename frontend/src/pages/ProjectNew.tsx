import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Agent, LibraryRoom, MemberInput, ProjectInput, ProjectRole, RoomLink, api } from "../api";
import MembersEditor from "../components/MembersEditor";
import ProjectDraftHelper from "../components/ProjectDraftHelper";
import ProjectFields from "../components/ProjectFields";
import RoomsEditor from "../components/RoomsEditor";

export default function ProjectNew() {
  const navigate = useNavigate();
  const [fields, setFields] = useState<ProjectInput>({
    name: "",
    goal: "",
    done_criteria: "",
    due_date: null,
    require_plan_approval: true,
    auto_manage: true,
  });
  const [members, setMembers] = useState<MemberInput[]>([]);
  const [links, setLinks] = useState<RoomLink[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [rooms, setRooms] = useState<LibraryRoom[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.agents(), api.projectRoles(), api.rooms()])
      .then(([a, r, lib]) => {
        setAgents(a);
        setRoles(r);
        setRooms(lib);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const project = await api.createProject({ ...fields, status: "active", members, rooms: links });
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <p className="breadcrumb">
        <Link to="/projects">プロジェクト</Link> / 立ち上げ
      </p>
      <h1>プロジェクトを立ち上げる</h1>
      <ProjectDraftHelper
        agents={agents}
        roles={roles}
        onDraft={(d) => {
          setFields((f) => ({ ...f, name: d.name, goal: d.goal, done_criteria: d.done_criteria }));
          setMembers(d.members.map(({ agent_id, role_id, is_primary }) => ({ agent_id, role_id, is_primary })));
          setLinks(d.rooms.map(({ room, access }) => ({ room, access })));
        }}
        onHired={(agent, roleId) => {
          setAgents((a) => [...a, agent]);
          setMembers((m) => [...m, { agent_id: agent.id, role_id: roleId, is_primary: false }]);
        }}
      />
      <form className="form" onSubmit={submit}>
        <section className="card form">
          <h2>概要</h2>
          <ProjectFields value={fields} onChange={setFields} />
        </section>
        <section className="card">
          <h2>メンバーとロール</h2>
          <p className="muted small">マネージャーを1人以上アサインします。「窓口」のマネージャーがオフィス長からの依頼を受けます。</p>
          <MembersEditor agents={agents} roles={roles} value={members} onChange={setMembers} />
        </section>
        <section className="card">
          <h2>資料室</h2>
          <RoomsEditor rooms={rooms} value={links} onChange={setLinks} />
        </section>
        {error && <p className="status bad">{error}</p>}
        <div className="form-actions">
          <button type="submit" className="btn primary" disabled={saving}>{saving ? "作成中…" : "立ち上げる"}</button>
          <Link to="/projects" className="btn">キャンセル</Link>
        </div>
      </form>
    </>
  );
}
