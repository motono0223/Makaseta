import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  Agent,
  LibraryRoom,
  MemberInput,
  Project,
  ProjectInput,
  ProjectRole,
  ProjectStatus,
  RoomLink,
  Task,
  TaskInput,
  TaskStatus,
  api,
} from "../api";
import Avatar from "../components/Avatar";
import Kanban from "../components/Kanban";
import ProjectThread from "../components/ProjectThread";
import MembersEditor from "../components/MembersEditor";
import ProjectFields from "../components/ProjectFields";
import RoomsEditor from "../components/RoomsEditor";
import TaskDialog from "../components/TaskDialog";
import { useThread } from "../components/ThreadDrawer";
import { libraryPath } from "../format";
import { PROJECT_STATUS } from "../labels";
import { usePolling } from "../usePolling";

type Tab = "board" | "thread" | "settings";

export default function ProjectDetail() {
  const projectId = Number(useParams().id);
  const navigate = useNavigate();
  const openThread = useThread();
  const [params, setParams] = useSearchParams();
  const tab: Tab = (["board", "thread", "settings"] as const).find((t) => t === params.get("tab")) ?? "board";
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const openTaskId = params.get("task");
  const editing: Task | "new" | null =
    openTaskId === "new" ? "new" : openTaskId ? tasks.find((t) => t.id === Number(openTaskId)) ?? null : null;
  const setEditing = (t: Task | "new" | null) => {
    const next = new URLSearchParams(params);
    if (t === null) next.delete("task");
    else next.set("task", t === "new" ? "new" : String(t.id));
    setParams(next);
  };
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.project(projectId).then(setProject).catch((e: Error) => setError(e.message));
    api.tasks(projectId).then(setTasks).catch((e: Error) => setError(e.message));
  }, [projectId]);

  const busy = tasks.some((t) => t.status === "in_progress" || t.status === "waiting");
  usePolling(load, busy ? 3000 : 10000);

  async function moveTask(task: Task, status: TaskStatus, position: number) {
    setError(null);
    // Show the move right away; the server response settles the final order.
    setTasks((ts) => ts.map((t) => (t.id === task.id ? { ...t, status, rank: position - 0.5 } : t)));
    try {
      await api.moveTask(task.id, status, position);
    } catch (e) {
      setError((e as Error).message);
    }
    load();
  }

  async function saveTask(input: TaskInput) {
    if (editing === "new") await api.createTask(projectId, input);
    else if (editing) await api.updateTask(editing.id, input);
    setEditing(null);
    load();
  }

  async function changeStatus(status: ProjectStatus) {
    setError(null);
    try {
      setProject(await api.updateProject(projectId, { status }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!project) return error ? <p className="status bad">{error}</p> : <p className="muted">読み込み中…</p>;

  return (
    <>
      <p className="breadcrumb">
        <Link to="/projects">プロジェクト</Link> / {project.name}
      </p>
      <div className="page-header">
        <div className="grow">
          <h1>{project.name}</h1>
          {project.goal && <p className="lead">{project.goal}</p>}
        </div>
        <select className="status-select" value={project.status} onChange={(e) => changeStatus(e.target.value as ProjectStatus)}
          aria-label="プロジェクトの状態">
          {(Object.keys(PROJECT_STATUS) as ProjectStatus[]).map((s) => (
            <option key={s} value={s}>{PROJECT_STATUS[s]}</option>
          ))}
        </select>
      </div>

      <div className="member-strip">
        {project.members.map((m) => (
          <button key={m.agent.id} type="button" className="member-chip" title="スレッドを開く" onClick={() => openThread(m.agent.id)}>
            <Avatar name={m.agent.name} color={m.agent.avatar_color} size={28} />
            <span>
              {m.agent.name}
              <span className="muted small"> {m.role.name}{m.is_primary && "・窓口"}</span>
            </span>
          </button>
        ))}
        {project.rooms.map((r) => (
          <Link key={r.room} to={libraryPath(r.room)} className="member-chip room-chip">
            📁 {r.room}
            <span className="muted small">{r.access === "write" ? "読み書き" : "読み取り"}</span>
          </Link>
        ))}
      </div>

      <nav className="tabs">
        <button type="button" className={tab === "board" ? "active" : ""} onClick={() => setParams({})}>カンバン</button>
        <button type="button" className={tab === "thread" ? "active" : ""} onClick={() => setParams({ tab: "thread" })}>
          スレッド
        </button>
        <button type="button" className={tab === "settings" ? "active" : ""} onClick={() => setParams({ tab: "settings" })}>
          設定
        </button>
      </nav>

      {error && <p className="status bad">{error}</p>}

      {tab === "board" && (
        <Kanban tasks={tasks} members={project.members} onOpen={setEditing} onAdd={() => setEditing("new")}
          onMove={moveTask} />
      )}
      {tab === "thread" && <ProjectThread project={project} tasks={tasks} onChanged={load} />}
      {tab === "settings" && (
        <ProjectSettings project={project} onSaved={setProject} onDeleted={() => navigate("/projects")} />
      )}

      {editing && (
        <TaskDialog
          task={editing === "new" ? null : editing}
          tasks={tasks}
          members={project.members}
          onSave={saveTask}
          onDelete={editing === "new" ? undefined : async () => {
            await api.deleteTask(editing.id);
            setEditing(null);
            load();
          }}
          onClose={() => setEditing(null)}
          onChanged={load}
        />
      )}
    </>
  );
}

function ProjectSettings({ project, onSaved, onDeleted }: {
  project: Project;
  onSaved: (p: Project) => void;
  onDeleted: () => void;
}) {
  const [fields, setFields] = useState<ProjectInput>(project);
  const [members, setMembers] = useState<MemberInput[]>(
    project.members.map((m) => ({ agent_id: m.agent.id, role_id: m.role.id, is_primary: m.is_primary })),
  );
  const [links, setLinks] = useState<RoomLink[]>(project.rooms);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [roles, setRoles] = useState<ProjectRole[]>([]);
  const [rooms, setRooms] = useState<LibraryRoom[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.agents(true), api.projectRoles(), api.rooms()])
      .then(([a, r, lib]) => {
        setAgents(a);
        setRoles(r);
        setRooms(lib);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  async function run(action: () => Promise<Project>, done: string) {
    setError(null);
    setNotice(null);
    try {
      onSaved(await action());
      setNotice(done);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function saveFields(e: FormEvent) {
    e.preventDefault();
    const { name, goal, done_criteria, due_date, require_plan_approval, auto_manage } = fields;
    await run(() => api.updateProject(project.id, { name, goal, done_criteria, due_date, require_plan_approval, auto_manage }),
      "概要を保存しました");
  }

  async function remove() {
    if (!window.confirm(`プロジェクト「${project.name}」を削除しますか？タスクも削除されます。資料室のファイルは残ります。`)) return;
    try {
      await api.deleteProject(project.id);
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      {notice && <p className="status ok">{notice}</p>}
      {error && <p className="status bad">{error}</p>}
      <section className="card">
        <form className="form" onSubmit={saveFields}>
          <h2>概要</h2>
          <ProjectFields value={fields} onChange={setFields} />
          <div className="form-actions">
            <button type="submit" className="btn primary">概要を保存</button>
          </div>
        </form>
      </section>
      <section className="card">
        <h2>メンバーとロール</h2>
        <MembersEditor agents={agents} roles={roles} value={members} onChange={setMembers} />
        <div className="form-actions spaced">
          <button type="button" className="btn primary"
            onClick={() => run(() => api.setMembers(project.id, members), "メンバーを保存しました")}>
            メンバーを保存
          </button>
        </div>
      </section>
      <section className="card">
        <h2>資料室</h2>
        <RoomsEditor rooms={rooms} value={links} onChange={setLinks} />
        <div className="form-actions spaced">
          <button type="button" className="btn primary"
            onClick={() => run(() => api.setRooms(project.id, links), "資料室のリンクを保存しました")}>
            資料室を保存
          </button>
        </div>
      </section>
      {project.status === "archived" && (
        <p className="footnote">
          <button type="button" className="link-button danger small" onClick={remove}>このプロジェクトを削除</button>
        </p>
      )}
    </>
  );
}
