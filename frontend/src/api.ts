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
  search: (text: string, roomName?: string) =>
    request<SearchHit[]>("GET", `/api/library/search?${q(roomName ? { q: text, room: roomName } : { q: text })}`),
};
