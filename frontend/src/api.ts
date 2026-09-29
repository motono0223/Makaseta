export type Health = {
  status: "ok" | "degraded";
  version: string;
  database: { ok: boolean; detail: string };
  storage: { ok: boolean; path: string };
};

export type ModelProfile = {
  name: string;
  label: string;
  provider: string;
  model: string;
  kind: string;
  supports_tools: boolean;
  available: boolean;
  reason: string;
  is_default: boolean;
};

export type Skill = {
  id: number;
  key: string | null;
  name: string;
  description: string;
  tools: string[];
  builtin: boolean;
};

export type AgentTemplate = {
  key: string;
  title: string;
  description: string;
  personality: string;
  instructions: string;
  skill_keys: string[];
  avatar_color: string;
};

export type AgentStatus = "idle" | "working" | "error";

export type Agent = {
  id: number;
  name: string;
  title: string;
  avatar_color: string;
  personality: string;
  instructions: string;
  model_profile: string;
  status: AgentStatus;
  active: boolean;
  retired_at: string | null;
  template_key: string | null;
  skills: Skill[];
  created_at: string;
  updated_at: string;
};

export type AgentInput = {
  name: string;
  title: string;
  avatar_color: string;
  personality: string;
  instructions: string;
  model_profile: string;
  skill_ids: number[];
  template_key?: string | null;
};

export type LibraryRoom = {
  name: string;
  description: string;
  documents: number;
  total_size: number;
  updated_at: string | null;
};

export type LibraryEntry = {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  modified_at: string | null;
  indexed: boolean;
  text_chars: number;
  extract_error: string;
  created_by_kind: string | null;
};

export type TextView = {
  path: string;
  editable: boolean;
  source: "raw" | "extracted" | "none";
  content: string;
  extract_error: string;
};

export type SearchHit = { room: string; path: string; snippet: string; size: number };

export type LibraryStatus = {
  host_path: string;
  scanning: boolean;
  last_scan_at: string | null;
  last_result: Record<string, number>;
  documents: number;
};

export type ProjectStatus = "planning" | "active" | "paused" | "done" | "archived";
export type TaskStatus = "backlog" | "in_progress" | "waiting" | "review" | "done";
export type Priority = "high" | "normal" | "low";

export type ProjectRole = { id: number; key: string | null; name: string; description: string; is_manager: boolean };
export type AgentBrief = Pick<Agent, "id" | "name" | "title" | "avatar_color" | "status" | "active">;
export type ProjectMember = { agent: AgentBrief; role: ProjectRole; is_primary: boolean };
export type RoomLink = { room: string; access: "read" | "write"; exists?: boolean };

export type Project = {
  id: number;
  name: string;
  goal: string;
  done_criteria: string;
  due_date: string | null;
  status: ProjectStatus;
  require_plan_approval: boolean;
  members: ProjectMember[];
  rooms: RoomLink[];
  task_counts: Partial<Record<TaskStatus, number>>;
  created_at: string;
  updated_at: string;
};

export type ProjectInput = {
  name: string;
  goal: string;
  done_criteria: string;
  due_date: string | null;
  status?: ProjectStatus;
  require_plan_approval: boolean;
};

export type MemberInput = { agent_id: number; role_id: number; is_primary: boolean };

export type Task = {
  id: number;
  project_id: number;
  title: string;
  instructions: string;
  expected_output: string;
  status: TaskStatus;
  priority: Priority;
  due_date: string | null;
  assignee_id: number | null;
  reviewer_id: number | null;
  requested_by_agent_id: number | null;
  rank: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type TaskInput = {
  title: string;
  instructions: string;
  expected_output: string;
  priority: Priority;
  due_date: string | null;
  assignee_id: number | null;
  reviewer_id: number | null;
  status?: TaskStatus;
};

export type Assignment = {
  project_id: number;
  project_name: string;
  project_status: ProjectStatus;
  role: ProjectRole;
  is_primary: boolean;
  tasks: Task[];
};

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method,
    headers: body === undefined || isForm ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(await errorMessage(res));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString();
const room = (name: string) => `/api/library/rooms/${encodeURIComponent(name)}`;

export const libraryUrl = {
  download: (roomName: string, path: string) => `${room(roomName)}/download?${q({ path })}`,
};

async function errorMessage(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg ?? "").join(" / ");
    }
  } catch {
    // not JSON
  }
  return `${res.status} ${res.statusText}`;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  modelProfiles: () => request<ModelProfile[]>("GET", "/api/settings/models"),
  skills: () => request<Skill[]>("GET", "/api/skills"),
  agentTemplates: () => request<AgentTemplate[]>("GET", "/api/agent-templates"),
  agents: (includeRetired = false) =>
    request<Agent[]>("GET", `/api/agents${includeRetired ? "?include_retired=true" : ""}`),
  agent: (id: number) => request<Agent>("GET", `/api/agents/${id}`),
  hireAgent: (input: AgentInput) => request<Agent>("POST", "/api/agents", input),
  updateAgent: (id: number, input: Partial<AgentInput>) => request<Agent>("PATCH", `/api/agents/${id}`, input),
  retireAgent: (id: number) => request<Agent>("POST", `/api/agents/${id}/retire`),
  rehireAgent: (id: number) => request<Agent>("POST", `/api/agents/${id}/rehire`),

  libraryStatus: () => request<LibraryStatus>("GET", "/api/library/status"),
  rescanLibrary: () => request<Record<string, number>>("POST", "/api/library/rescan"),
  rooms: () => request<LibraryRoom[]>("GET", "/api/library/rooms"),
  createRoom: (name: string, description: string) =>
    request<LibraryRoom>("POST", "/api/library/rooms", { name, description }),
  updateRoom: (name: string, description: string) => request<unknown>("PATCH", room(name), { description }),
  deleteRoom: (name: string) => request<void>("DELETE", room(name)),
  entries: (roomName: string, path: string) =>
    request<LibraryEntry[]>("GET", `${room(roomName)}/entries?${q({ path })}`),
  viewText: (roomName: string, path: string) => request<TextView>("GET", `${room(roomName)}/text?${q({ path })}`),
  createText: (roomName: string, path: string, content: string) =>
    request<LibraryEntry>("POST", `${room(roomName)}/text`, { path, content }),
  saveText: (roomName: string, path: string, content: string) =>
    request<LibraryEntry>("PUT", `${room(roomName)}/text`, { path, content }),
  createFolder: (roomName: string, path: string) =>
    request<LibraryEntry>("POST", `${room(roomName)}/folders`, { path }),
  deleteEntry: (roomName: string, path: string) =>
    request<void>("DELETE", `${room(roomName)}/entries?${q({ path })}`),
  upload: (roomName: string, folder: string, files: File[], overwrite = false) => {
    const form = new FormData();
    form.append("folder", folder);
    form.append("overwrite", String(overwrite));
    files.forEach((f) => form.append("files", f));
    return request<LibraryEntry[]>("POST", `${room(roomName)}/upload`, form);
  },
  projectRoles: () => request<ProjectRole[]>("GET", "/api/project-roles"),
  projects: (includeArchived = false) =>
    request<Project[]>("GET", `/api/projects${includeArchived ? "?include_archived=true" : ""}`),
  project: (id: number) => request<Project>("GET", `/api/projects/${id}`),
  createProject: (input: ProjectInput & { members: MemberInput[]; rooms: RoomLink[] }) =>
    request<Project>("POST", "/api/projects", input),
  updateProject: (id: number, input: Partial<ProjectInput>) => request<Project>("PATCH", `/api/projects/${id}`, input),
  setMembers: (id: number, members: MemberInput[]) => request<Project>("PUT", `/api/projects/${id}/members`, members),
  setRooms: (id: number, rooms: RoomLink[]) =>
    request<Project>("PUT", `/api/projects/${id}/rooms`, rooms.map(({ room, access }) => ({ room, access }))),
  deleteProject: (id: number) => request<void>("DELETE", `/api/projects/${id}`),
  tasks: (projectId: number) => request<Task[]>("GET", `/api/projects/${projectId}/tasks`),
  createTask: (projectId: number, input: TaskInput) => request<Task>("POST", `/api/projects/${projectId}/tasks`, input),
  updateTask: (id: number, input: Partial<TaskInput>) => request<Task>("PATCH", `/api/tasks/${id}`, input),
  moveTask: (id: number, status: TaskStatus, position: number) =>
    request<Task>("POST", `/api/tasks/${id}/move`, { status, position }),
  deleteTask: (id: number) => request<void>("DELETE", `/api/tasks/${id}`),
  assignments: (agentId: number) => request<Assignment[]>("GET", `/api/agents/${agentId}/assignments`),

  search: (text: string, roomName?: string) =>
    request<SearchHit[]>("GET", `/api/library/search?${q(roomName ? { q: text, room: roomName } : { q: text })}`),
};
