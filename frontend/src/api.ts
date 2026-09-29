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

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => getJson<Health>("/api/health"),
  modelProfiles: () => getJson<ModelProfile[]>("/api/settings/models"),
};
