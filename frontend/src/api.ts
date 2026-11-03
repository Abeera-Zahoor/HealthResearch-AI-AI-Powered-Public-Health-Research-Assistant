import type { Health, ResearchRun, RunRequest, RunSummary } from "./types";

export class ApiError extends Error {}

const NETWORK_MESSAGE =
  "Cannot reach the HealthResearch AI backend. Make sure the backend window is open and running on port 8000, then try again.";

/** Turn FastAPI error bodies ({detail: "text"} or {detail: [{msg}, ...]}) into one readable sentence. */
export function describeError(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item as { msg?: unknown })?.msg)
      .filter((msg): msg is string => typeof msg === "string")
      .map((msg) => msg.replace(/^Value error,\s*/i, ""));
    if (messages.length) return messages.join(" ");
  }
  return `The server returned an error (HTTP ${status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(NETWORK_MESSAGE);
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      /* not JSON - e.g. the dev proxy could not reach the backend */
    }
    if (response.status >= 502 && body === null) throw new ApiError(NETWORK_MESSAGE);
    throw new ApiError(describeError(body, response.status));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  startRun: (body: RunRequest) => request<ResearchRun>("/api/research", { method: "POST", body: JSON.stringify(body) }),
  getRun: (id: string) => request<ResearchRun>(`/api/research/${encodeURIComponent(id)}`),
  listRuns: () => request<RunSummary[]>("/api/research"),
  deleteRun: (id: string) => request<void>(`/api/research/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
