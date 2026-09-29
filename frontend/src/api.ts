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

export class ApiError extends Error {}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(await errorMessage(res));
  }
  return (await res.json()) as T;
}

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
};
