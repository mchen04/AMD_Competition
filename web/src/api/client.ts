import type {
  ActiveProviderResponse,
  CheckResponse,
  IncidentResponse,
  ResetResponse,
  RunResultResponse,
  RunStartedResponse,
  SnapshotResponse,
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
};
