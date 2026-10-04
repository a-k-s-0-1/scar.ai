import type {
  ResearchSession,
  KnowledgeGraph,
  ResearchReport,
  StartResearchRequest,
  SessionListResponse,
  SessionSummary,
  SessionEventsResponse,
  TrajectoryResponse,
  PredictionsResponse,
  DecisionInspectorResponse,
  SessionStateResponse,
  DatasetStats,
  DatasetResponse,
  OfflinePolicy,
  DatasetBuildResponse,
  PoliciesResponse,
  EvaluationReport,
  EvaluationResultsResponse,
  EvaluationResultDetail,
  EvaluationRunRequest,
  MemoryListResponse,
  MemoryConflictsResponse,
  MemorySessionResponse,
  MemoryPromoteResponse,
} from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
// Configurable per environment; the development default matches the backend's
// own default key so a fresh clone works without setup.
const API_KEY =
  process.env.NEXT_PUBLIC_API_KEY || "dev_api_key_jev_ikf_2026";

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...(options?.headers || {}),
    },
  });

  if (!res.ok) {
    const raw = await res.text();
    let message = raw || `HTTP ${res.status}`;
    // Prefer the API's standard error envelope ({"error": {"message": ...}}) so
    // users see the human-readable reason instead of a raw JSON blob.
    try {
      const parsed = JSON.parse(raw) as { error?: { message?: string } };
      if (parsed?.error?.message) {
        message = parsed.error.message;
      }
    } catch {
      // Non-JSON body (proxy error page, plain text): keep the raw text.
    }
    throw new Error(message);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return {} as T;
  }

  return res.json() as Promise<T>;
}

// ─── Sessions ─────────────────────────────────────────────────────────────────

export async function startResearch(
  body: StartResearchRequest
): Promise<ResearchSession> {
  return apiFetch<ResearchSession>("/api/research/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function stopResearch(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/research/${sessionId}/stop`, { method: "POST" });
}

export async function getSession(
  sessionId: string
): Promise<ResearchSession> {
  return apiFetch<ResearchSession>(`/api/research/${sessionId}`);
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await apiFetch<SessionListResponse>("/api/sessions");
  return res.sessions || [];
}

export async function deleteSession(sessionId: string): Promise<void> {
  return apiFetch<void>(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

/**
 * Persisted progress events for a session.
 *
 * Live updates only exist on the WebSocket, so a finished investigation has no
 * stream left to subscribe to — these events are what make its activity log
 * replayable.
 */
export async function listSessionEvents(
  sessionId: string,
  afterSeq = 0,
  limit = 500
): Promise<SessionEventsResponse> {
  return apiFetch<SessionEventsResponse>(
    `/api/research/${sessionId}/events?after_seq=${afterSeq}&limit=${limit}`
  );
}

/**
 * Re-run report synthesis over the evidence a finished run already gathered.
 *
 * Synthesis is the one step that degrades silently when a provider rate limits,
 * so this recovers a run with a rule-based summary without re-running research.
 */
export async function retryReportSynthesis(
  sessionId: string
): Promise<ResearchReport> {
  const res = await apiFetch<{ report_data: ResearchReport }>(
    `/api/research/${sessionId}/retry-synthesis`,
    { method: "POST" }
  );
  return res.report_data;
}

// ─── Knowledge & Reports ─────────────────────────────────────────────────────

export async function getKnowledgeGraph(
  sessionId: string
): Promise<KnowledgeGraph> {
  return apiFetch<KnowledgeGraph>(`/api/research/${sessionId}/knowledge`);
}

export async function getReport(
  sessionId: string
): Promise<ResearchReport> {
  return apiFetch<ResearchReport>(`/api/research/${sessionId}/report`);
}

export async function getHealth(): Promise<{
  status: string;
  environment: string;
  timestamp: string;
}> {
  return apiFetch("/health");
}// ─── V2: trajectory / decision inspector / state ─────────────────────────────
export async function getSessionTrajectory(
  sessionId: string,
  limit = 200
): Promise<TrajectoryResponse> {
  return apiFetch<TrajectoryResponse>(`/api/research/${sessionId}/trajectory?limit=${limit}`);
}

export async function getDecisionInspector(
  sessionId: string
): Promise<DecisionInspectorResponse> {
  return apiFetch<DecisionInspectorResponse>(`/api/research/${sessionId}/decisions`);
}

export async function getSessionState(
  sessionId: string
): Promise<SessionStateResponse> {
  return apiFetch<SessionStateResponse>(`/api/research/${sessionId}/state`);
}

export async function getSessionPredictions(
  sessionId: string,
  limit = 200
): Promise<PredictionsResponse> {
  return apiFetch<PredictionsResponse>(`/api/research/${sessionId}/predictions?limit=${limit}`);
}

// ─── V2: offline dataset / policies / evaluation ──────────────────────────────
export async function getDataset(
  sessionIds?: string | null,
  includeIncomplete = false,
  limit = 1000
): Promise<DatasetResponse> {
  const params = new URLSearchParams();
  if (includeIncomplete) params.set("include_incomplete", "true");
  if (sessionIds) params.set("session_ids", sessionIds);
  params.set("limit", String(limit));
  return apiFetch<DatasetResponse>(`/api/evaluation/dataset?${params.toString()}`);
}

export async function getDatasetStats(
  includeIncomplete = false
): Promise<DatasetStats> {
  const params = new URLSearchParams();
  if (includeIncomplete) params.set("include_incomplete", "true");
  return apiFetch<DatasetStats>(`/api/evaluation/dataset/stats?${params.toString()}`);
}

export async function buildDataset(
  opts: {
    sessionIds?: string[] | null;
    includeIncomplete?: boolean;
    train?: boolean;
    activate?: boolean;
    policyName?: string;
    backfill?: boolean;
  } = {}
): Promise<DatasetBuildResponse> {
  return apiFetch<DatasetBuildResponse>("/api/evaluation/dataset/build", {
    method: "POST",
    body: JSON.stringify({
      session_ids: opts.sessionIds ?? null,
      include_incomplete: opts.includeIncomplete ?? false,
      train: opts.train ?? false,
      activate: opts.activate ?? true,
      policy_name: opts.policyName ?? "jev-baseline-shadow",
      backfill: opts.backfill ?? false,
    }),
  });
}

export async function runEvaluation(
  opts: EvaluationRunRequest = { policy: "rl", baseline: "jev" }
): Promise<EvaluationReport> {
  return apiFetch<EvaluationReport>("/api/evaluation/run", {
    method: "POST",
    body: JSON.stringify(opts),
  });
}

export async function listEvaluationResults(
  limit = 20
): Promise<EvaluationResultsResponse> {
  return apiFetch<EvaluationResultsResponse>(`/api/evaluation/results?limit=${limit}`);
}

export async function getEvaluationResult(
  runId: string
): Promise<EvaluationResultDetail> {
  return apiFetch<EvaluationResultDetail>(`/api/evaluation/results/${runId}`);
}

export async function listPolicies(): Promise<PoliciesResponse> {
  return apiFetch<PoliciesResponse>(`/api/evaluation/policies`);
}

export async function trainPolicy(
  opts: {
    includeIncomplete?: boolean;
    activate?: boolean;
    name?: string;
  } = {}
): Promise<DatasetBuildResponse> {
  const params = new URLSearchParams();
  if (opts.includeIncomplete) params.set("include_incomplete", "true");
  if (opts.activate !== undefined) params.set("activate", String(opts.activate));
  if (opts.name) params.set("name", opts.name);
  return apiFetch<DatasetBuildResponse>(`/api/evaluation/policies/train?${params.toString()}`, {
    method: "POST",
  });
}

export async function activatePolicy(policyId: string): Promise<{ policy: OfflinePolicy; message: string }> {
  return apiFetch<{ policy: OfflinePolicy; message: string }>(`/api/evaluation/policies/${policyId}/activate`, {
    method: "POST",
  });
}
export async function getRewardFormula(): Promise<{
  reward: Record<string, unknown>;
  actions: { executable: string[]; all: Record<string, unknown>[] };
  dataset_version: string;
}> {
  return apiFetch(`/api/evaluation/reward-formula`);
}

// ─── V2: long-term memory ─────────────────────────────────────────────────────
export async function listMemory(
  kind?: string,
  search?: string,
  limit = 200
): Promise<MemoryListResponse> {
  const params = new URLSearchParams();
  if (kind) params.set("kind", kind);
  if (search) params.set("search", search);
  params.set("limit", String(limit));
  return apiFetch<MemoryListResponse>(`/api/memory?${params.toString()}`);
}

export async function searchMemory(
  query: string,
  limit = 50
): Promise<MemoryListResponse> {
  const params = new URLSearchParams();
  // The backend's search and recall routes both take `q`, not `query`.
  params.set("q", query);
  params.set("limit", String(limit));
  return apiFetch<MemoryListResponse>(`/api/memory/search?${params.toString()}`);
}

export async function getMemoryForSession(
  sessionId: string
): Promise<MemorySessionResponse> {
  return apiFetch<MemorySessionResponse>(`/api/memory/session/${sessionId}`);
}

export async function getMemoryConflicts(
  statusFilter?: string | null
): Promise<MemoryConflictsResponse> {
  const params = new URLSearchParams();
  if (statusFilter) params.set("status", statusFilter);
  return apiFetch<MemoryConflictsResponse>(`/api/memory/conflicts?${params.toString()}`);
}

export async function promoteMemory(
  sessionId: string,
  maxClaims = 25,
  maxSources = 10
): Promise<MemoryPromoteResponse> {
  return apiFetch<MemoryPromoteResponse>(`/api/memory/promote`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, max_claims: maxClaims, max_sources: maxSources }),
  });
}
export async function memoryStats(): Promise<{
  total: number;
  kinds: Record<string, number>;
  embedded: number;
  provider: string;
  mean_weight: number;
  max_items: number;
  half_life_days: number;
}> {
  return apiFetch(`/api/memory/stats`);
}
export async function recallMemory(
  query: string,
  limit = 20
): Promise<MemoryListResponse> {
  const params = new URLSearchParams();
  params.set("q", query);
  params.set("limit", String(limit));
  return apiFetch<MemoryListResponse>(`/api/memory/recall?${params.toString()}`);
}
export async function pruneMemory(): Promise<{ removed_decayed: number; removed_overflow: number }> {
  return apiFetch(`/api/memory/prune`, { method: "POST" });
}
export async function forgetMemoryItem(itemId: string): Promise<void> {
  return apiFetch<void>(`/api/memory/${itemId}`, { method: "DELETE" });
}

// ─── WebSocket factory ────────────────────────────────────────────────────────
export function createResearchSocket(sessionId: string): WebSocket {
  const wsBase =
    process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";
  // Sockets cannot send headers, so the API key travels as a query parameter;
  // the server refuses the connection before accepting it when the key is wrong.
  return new WebSocket(
    `${wsBase}/api/research/ws/${sessionId}?api_key=${encodeURIComponent(API_KEY)}`
  );
}
