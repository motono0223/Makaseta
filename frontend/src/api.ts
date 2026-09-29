export type Health = {
  status: "ok" | "degraded";
  version: string;
  database: { ok: boolean; detail: string };
  storage: { ok: boolean; path: string };
  sandbox: { ok: boolean };
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
  source: "builtin" | "package";
  folder: string | null;
  enabled: boolean;
};

export type SkillFile = { path: string; size: number; script: boolean };

export type SkillDetail = Skill & {
  instructions: string;
  source_url: string;
  agents: string[];
  files: SkillFile[];
  body: string;
  license: string;
  updated_at: string;
};

export type SkillPreview = {
  stage_id: string;
  name: string;
  folder: string;
  description: string;
  license: string;
  body: string;
  files: SkillFile[];
  exists: boolean;
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
  leave_started_at: string | null;
  template_key: string | null;
  skills: Skill[];
  created_at: string;
  updated_at: string;
};

export type AgentNote = {
  id: number;
  body: string;
  source: "reflection" | "manager";
  task_id: number | null;
  task_title: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentStats = {
  tasks_done: number;
  tasks_open: number;
  rejections: number;
  first_pass_rate: number | null;
  projects: number;
  notes: number;
  cost_usd: number;
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
  confidential: boolean;
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
export type RoomLink = { room: string; access: "read" | "write"; exists?: boolean; confidential?: boolean };
export type FileVersion = { version: string; size: number; saved_at: string };

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
  plan_id: number | null;
  depends_on: number[];
  review_stage: "peer" | "manager" | null;
  peer_rounds: number;
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

export type ProjectDraft = {
  name: string;
  goal: string;
  done_criteria: string;
  members: { agent_id: number; role_id: number; is_primary: boolean; reason: string }[];
  new_members: {
    name: string;
    title: string;
    role_id: number;
    template_key: string | null;
    clone_of: number | null;
    reason: string;
  }[];
  rooms: { room: string; access: "read" | "write"; reason: string }[];
};

export type Assignment = {
  project_id: number;
  project_name: string;
  project_status: ProjectStatus;
  role: ProjectRole;
  is_primary: boolean;
  tasks: Task[];
};

export type RunStep = { id: number; kind: "text" | "tool_call" | "tool_result" | "error" | "info"; name: string; content: string; created_at: string };
export type Run = {
  id: number;
  kind: "task" | "chat" | "plan" | "reflect" | "review";
  agent_id: number;
  status: "queued" | "running" | "waiting" | "succeeded" | "failed" | "cancelled" | "interrupted";
  steps: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  error: string;
  awaiting_review: boolean;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  log: RunStep[];
};
export type Deliverable = {
  id: number;
  agent_id: number | null;
  room: string;
  path: string;
  content: string;
  status: "draft" | "approved" | "rejected" | "superseded";
  created_at: string;
  decided_at: string | null;
  overwrites: boolean;
  file_size: number | null;
};
export type Message = {
  id: number;
  agent_id: number | null;
  project_id: number | null;
  task_id: number | null;
  run_id: number | null;
  sender: "manager" | "agent" | "system";
  kind: "chat" | "report" | "question" | "answer" | "instruction" | "review" | "request" | "plan" | "consult";
  body: string;
  created_at: string;
  awaiting_answer: boolean;
};

export type PlanItem = {
  title: string;
  instructions: string;
  expected_output: string;
  assignee_id: number | null;
  assignee_name: string | null;
  reviewer_id: number | null;
  reviewer_name: string | null;
  priority: Priority;
  depends_on: number[];
};

export type Plan = {
  id: number;
  project_id: number;
  agent_id: number | null;
  request: string;
  status: "drafting" | "proposed" | "approved" | "cancelled";
  summary: string;
  items: PlanItem[];
  run_status: Run["status"] | null;
  run_error: string;
  task_ids: number[];
  created_at: string;
  decided_at: string | null;
};
export type TaskWork = {
  runs: Run[];
  deliverables: Deliverable[];
  question: Message | null;
  report: Message | null;
  peer_review: Message | null;
};
export type InboxItem = {
  kind: "question" | "review" | "failed" | "plan";
  task_id: number | null;
  plan_id: number | null;
  task_title: string;
  project_id: number;
  project_name: string;
  agent_id: number | null;
  agent_name: string | null;
  body: string;
  created_at: string;
};
export type UsageRow = { id: number | null; name: string; cost_usd: number; input_tokens: number; output_tokens: number };
export type UsageSummary = {
  month_spend_usd: string;
  monthly_budget_usd: number;
  by_agent: UsageRow[];
  by_project: UsageRow[];
};

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method,
    headers: body === undefined || isForm ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  });
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    // Session expired or missing: show the login screen.
    window.dispatchEvent(new Event("makaseta:logged-out"));
  }
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
  authStatus: () => request<{ required: boolean; authenticated: boolean }>("GET", "/api/auth/status"),
  login: (password: string) => request<{ ok: boolean }>("POST", "/api/auth/login", { password }),
  logout: () => request<{ ok: boolean }>("POST", "/api/auth/logout"),
  health: () => request<Health>("GET", "/api/health"),
  modelProfiles: () => request<ModelProfile[]>("GET", "/api/settings/models"),
  skills: () => request<Skill[]>("GET", "/api/skills"),
  skillDetails: () => request<SkillDetail[]>("GET", "/api/skills/details"),
  skillDetail: (id: number) => request<SkillDetail>("GET", `/api/skills/${id}/detail`),
  rescanSkills: () => request<SkillDetail[]>("POST", "/api/skills/rescan"),
  previewSkill: (url: string) => request<SkillPreview>("POST", "/api/skills/import/preview", { url }),
  installSkill: (stageId: string, replace: boolean) =>
    request<SkillDetail>("POST", "/api/skills/import/install", { stage_id: stageId, replace }),
  discardSkill: (stageId: string) => request<void>("DELETE", `/api/skills/import/${stageId}`),
  deleteSkill: (id: number) => request<void>("DELETE", `/api/skills/${id}`),
  agentTemplates: () => request<AgentTemplate[]>("GET", "/api/agent-templates"),
  agents: (includeOnLeave = false) =>
    request<Agent[]>("GET", `/api/agents${includeOnLeave ? "?include_on_leave=true" : ""}`),
  agent: (id: number) => request<Agent>("GET", `/api/agents/${id}`),
  cloneAgent: (id: number, name: string, copyNotes: boolean) =>
    request<Agent>("POST", `/api/agents/${id}/clone`, { name, copy_notes: copyNotes }),
  projectDraft: (idea: string) => request<ProjectDraft>("POST", "/api/assist/project-draft", { idea }),
  suggestNames: (theme: string, title: string) =>
    request<{ name: string; note: string }[]>("POST", "/api/agents/suggest-names", { theme, title }),
  hireAgent: (input: AgentInput) => request<Agent>("POST", "/api/agents", input),
  updateAgent: (id: number, input: Partial<AgentInput>) => request<Agent>("PATCH", `/api/agents/${id}`, input),
  notes: (agentId: number) => request<AgentNote[]>("GET", `/api/agents/${agentId}/notes`),
  addNote: (agentId: number, body: string) => request<AgentNote>("POST", `/api/agents/${agentId}/notes`, { body }),
  editNote: (noteId: number, body: string) => request<AgentNote>("PATCH", `/api/notes/${noteId}`, { body }),
  deleteNote: (noteId: number) => request<void>("DELETE", `/api/notes/${noteId}`),
  agentStats: (agentId: number) => request<AgentStats>("GET", `/api/agents/${agentId}/stats`),
  startLeave: (id: number) => request<Agent>("POST", `/api/agents/${id}/leave`),
  endLeave: (id: number) => request<Agent>("POST", `/api/agents/${id}/return`),

  libraryStatus: () => request<LibraryStatus>("GET", "/api/library/status"),
  rescanLibrary: () => request<Record<string, number>>("POST", "/api/library/rescan"),
  rooms: () => request<LibraryRoom[]>("GET", "/api/library/rooms"),
  createRoom: (name: string, description: string) =>
    request<LibraryRoom>("POST", "/api/library/rooms", { name, description }),
  updateRoom: (name: string, changes: { description?: string; confidential?: boolean }) =>
    request<unknown>("PATCH", room(name), changes),
  versions: (roomName: string, path: string) =>
    request<FileVersion[]>("GET", `${room(roomName)}/versions?${q({ path })}`),
  versionText: (roomName: string, path: string, version: string) =>
    request<TextView>("GET", `${room(roomName)}/versions/text?${q({ path, version })}`),
  restoreVersion: (roomName: string, path: string, version: string) =>
    request<unknown>("POST", `${room(roomName)}/versions/restore`, { path, version }),
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

  taskWork: (taskId: number) => request<TaskWork>("GET", `/api/tasks/${taskId}/work`),
  answerTask: (taskId: number, body: string) => request<Message>("POST", `/api/tasks/${taskId}/answer`, { body }),
  approveTask: (taskId: number) => request<Deliverable[]>("POST", `/api/tasks/${taskId}/approve`),
  rejectTask: (taskId: number, body: string) => request<Run>("POST", `/api/tasks/${taskId}/reject`, { body }),
  retryTask: (taskId: number) => request<Run>("POST", `/api/tasks/${taskId}/retry`),
  cancelTask: (taskId: number) => request<unknown>("POST", `/api/tasks/${taskId}/cancel`),
  agentThread: (agentId: number) => request<Message[]>("GET", `/api/agents/${agentId}/thread`),
  messageAgent: (agentId: number, body: string, answerRunId?: number) =>
    request<Message>("POST", `/api/agents/${agentId}/messages`, { body, answer_run_id: answerRunId ?? null }),
  answerRun: (runId: number, body: string) => request<Message>("POST", `/api/runs/${runId}/answer`, { body }),
  requestToManager: (projectId: number, body: string) =>
    request<Plan>("POST", `/api/projects/${projectId}/requests`, { body }),
  plans: (projectId: number) => request<Plan[]>("GET", `/api/projects/${projectId}/plans`),
  approvePlan: (planId: number) => request<Plan>("POST", `/api/plans/${planId}/approve`),
  rejectPlan: (planId: number, body: string) => request<Plan>("POST", `/api/plans/${planId}/reject`, { body }),
  cancelPlan: (planId: number) => request<Plan>("POST", `/api/plans/${planId}/cancel`),
  retryPlan: (planId: number) => request<Plan>("POST", `/api/plans/${planId}/retry`),
  projectThread: (projectId: number) => request<Message[]>("GET", `/api/projects/${projectId}/thread`),
  inbox: () => request<InboxItem[]>("GET", "/api/inbox"),
  usage: () => request<UsageSummary>("GET", "/api/usage/summary"),

  exportOffice: (includeWork: boolean) =>
    request<{ name: string; size: number }>("POST", "/api/office/export", { include_work: includeWork }),
  officeExports: () => request<{ name: string; size: number; created_at: string }[]>("GET", "/api/office/exports"),
  deleteOfficeExport: (name: string) => request<void>("DELETE", `/api/office/exports/${encodeURIComponent(name)}`),
  importOffice: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ backup: string; tables: Record<string, number>; created_at: string }>("POST", "/api/office/import", form);
  },

  search: (text: string, roomName?: string) =>
    request<SearchHit[]>("GET", `/api/library/search?${q(roomName ? { q: text, room: roomName } : { q: text })}`),
};
