import type {
  ActiveProviderResponse,
  BaselineState,
  CheckResponse,
  ConfigImportResponse,
  ConfigSelectResponse,
  ConfigsListResponse,
  IncidentResponse,
  ResetResponse,
  RunResultResponse,
  RunStartedResponse,
  SnapshotResponse,
  SupervisorRun,
} from "./types";

export class ApiError extends Error {
  status: number;
  payload: unknown;
  constructor(status: number, message: string, payload: unknown) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { error: text || res.statusText };
  }
  if (!res.ok) {
    const msg =
      (body && typeof body === "object" && "error" in body && typeof (body as { error: unknown }).error === "string"
        ? (body as { error: string }).error
        : null) || `HTTP ${res.status}`;
    throw new ApiError(res.status, msg, body);
  }
  return body as T;
}

export const api = {
  snapshot: () => request<SnapshotResponse>("/api/snapshot"),
  check: () => request<CheckResponse>("/api/check", { method: "POST", body: "{}" }),
  reset: () => request<ResetResponse>("/api/reset", { method: "POST", body: "{}" }),
  setActiveProvider: (providerId: string) =>
    request<ActiveProviderResponse>("/api/active-provider", {
      method: "POST",
      body: JSON.stringify({ provider_id: providerId }),
    }),
  startRun: (scenario: string | null, providerName: string | null) => {
    const body: Record<string, unknown> = { scenario };
    if (providerName) body.provider_name = providerName;
    return request<RunStartedResponse>("/api/run", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  runResult: (runId: string) => request<RunResultResponse>(`/api/run/${encodeURIComponent(runId)}`),
  incident: (id: string) => request<IncidentResponse>(`/api/incident/${encodeURIComponent(id)}`),
  listConfigs: () => request<ConfigsListResponse>("/api/configs"),
  selectConfig: (choice: { id?: string; path?: string; source?: string }) =>
    request<ConfigSelectResponse>("/api/configs/select", {
      method: "POST",
      body: JSON.stringify(choice),
    }),
  importConfig: (payload: { name: string; yaml: string; overwrite?: boolean; select?: boolean }) =>
    request<ConfigImportResponse>("/api/configs/import", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  baselinePin: () =>
    request<{ pinned: boolean; config_path: string; paths: number }>("/api/baseline/pin", {
      method: "POST",
      body: "{}",
    }),
  baselineUnpin: () =>
    request<{ unpinned: boolean }>("/api/baseline/unpin", { method: "POST", body: "{}" }),
  baselineRestore: () =>
    request<{ restored: boolean; config_path: string }>("/api/baseline/restore", {
      method: "POST",
      body: "{}",
    }),
  baselineDiff: () => request<BaselineState>("/api/baseline/diff"),
  superviseStart: (payload: { interval_seconds?: number; until_pass?: boolean; provider_name?: string }) =>
    request<{ run_id: string; diagnosis_provider: string; interval_seconds: number; until_pass: boolean }>(
      "/api/supervise/start",
      { method: "POST", body: JSON.stringify(payload) },
    ),
  superviseStop: (runId: string) =>
    request<{ run_id: string; stopping: boolean }>(`/api/supervise/${encodeURIComponent(runId)}/stop`, {
      method: "POST",
      body: "{}",
    }),
  superviseStatus: (runId: string) =>
    request<SupervisorRun>(`/api/supervise/${encodeURIComponent(runId)}`),
};
