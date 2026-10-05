/** Typed client for the NEXUS API. */
import type {
  EntityResponse,
  Health,
  QueryResult,
  RankedIncident,
  Stats,
} from "./types";

// Empty by default: requests are relative, so the app works when the backend
// serves the built frontend from the same origin (no CORS needed). Set
// VITE_API_BASE when the UI runs on a different origin, e.g. the Vite dev
// server (which also proxies /api to the backend).
const BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  base: BASE,
  health: () => request<Health>("/api/health"),
  stats: () => request<Stats>("/api/graph/stats"),
  overview: (focus?: string, depth = 2) =>
    request<import("./types").Graph>(
      `/api/graph/overview?depth=${depth}${focus ? `&focus=${encodeURIComponent(focus)}` : ""}`,
    ),
  incidents: () => request<{ count: number; incidents: RankedIncident[] }>("/api/incidents"),
  entity: (id: string) => request<EntityResponse>(`/api/entity/${encodeURIComponent(id)}`),
  query: (question: string, sessionId: string) =>
    request<QueryResult>("/api/query", {
      method: "POST",
      body: JSON.stringify({ question, session_id: sessionId }),
    }),
  memory: (text: string, sessionId: string) =>
    request<Record<string, unknown>>("/api/memory", {
      method: "POST",
      body: JSON.stringify({ text, session_id: sessionId }),
    }),
};
