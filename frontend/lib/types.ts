// ─── Core domain types matching backend schemas ─────────────────────────────

export type DepthLevel = "shallow" | "standard" | "deep";
export type SessionStatus =
  | "initializing"
  | "pending"
  | "running"
  | "completed"
  | "error"
  | "stopped";

export interface ResearchSession {
  id: string;
  question: string;
  depth: DepthLevel;
  status: SessionStatus;
  current_iteration?: number;
  iterations_completed?: number;
  max_iterations?: number;
  min_sources_required?: number;
  max_research_time_minutes?: number;
  total_sources?: number;
  total_claims?: number;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: string;
  question: string;
  depth: string;
  status: string;
  current_iteration: number;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  sources_count: number;
  claims_count: number;
}

export interface SessionListResponse {
  total: number;
  sessions: SessionSummary[];
}

export interface Source {
  id: string;
  url: string;
  title: string;
  credibility_score: number;
  content_preview?: string;
  published_date?: string;
  domain?: string;
}

export interface Citation {
  citation_number: number;
  source_id: string;
  url: string;
  title: string;
  credibility_score: number;
  published_at?: string;
}

export interface EvidenceItem {
  claim_id: string;
  claim: string;
  subject?: string;
  predicate?: string;
  object?: string;
  /** What the extractor sounded like; kept for older reports. */
  confidence: "high" | "medium" | "low";
  citations: number[];
  /** IKF 2.0: `high`/`medium`/`low` derived from evidence, not from the extractor. */
  evidence_band?: EvidenceBand | null;
  evidence_strength?: number | null;
  /** Per-factor breakdown: source quality, independence, recency, agreement, extraction. */
  evidence_components?: Record<string, number> | null;
  independent_sources?: number | null;
}

export type EvidenceBand = "high" | "medium" | "low";

/** One observation of a subject/predicate pair, pinned to a point in time. */
export interface ClaimVersion {
  claim_id: string;
  text: string;
  subject: string;
  predicate: string;
  value: string;
  valid_from?: number | null;
  valid_to?: number | null;
  validity_precision?: string;
  confidence: string;
  source_ids: string[];
  strength?: number | null;
  extracted_at?: string | null;
}

/** Every observation of one fact, ordered newest first. */
export interface VersionGroup {
  subject: string;
  predicate: string;
  /** `versioned` = the fact moved over time; `conflicted` = sources disagree now. */
  status: "single" | "versioned" | "conflicted";
  span: { from: number | null; to: number | null };
  conflicts: string[][];
  versions: ClaimVersion[];
}

/** Run-level evidence roll-up attached to report metadata. */
export interface EvidenceSummary {
  claims?: number;
  mean_strength?: number;
  high?: number;
  medium?: number;
  low?: number;
  sources?: number;
  strongest_claim_id?: string | null;
  weakest_claim_id?: string | null;
}

export interface Claim {
  id: string;
  content: string;
  confidence_score: number;
  source_id: string;
  iteration_found: number;
}

export interface ContradictionItem {
  id: string;
  claim_1: string;
  claim_2: string;
  severity: "low" | "medium" | "high";
  explanation?: string;
}

export interface Contradiction {
  id: string;
  claim_1_id: string;
  claim_2_id: string;
  severity: "low" | "medium" | "high";
  explanation: string;
}

export interface KnowledgeNode {
  id: string;
  label: string;
  entity_type: string;
  description?: string | null;
}

export interface KnowledgeEdge {
  id: string;
  from_node: string;
  to_node: string;
  label: string;
  strength: number;
}

export interface KnowledgeGraph {
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

export interface ResearchReport {
  session_id: string;
  question: string;
  depth?: string;
  executive_summary: string;
  key_findings: string[];
  evidence_table?: EvidenceItem[];
  /** Facts the run watched change over time, rather than disagreements. */
  versions?: VersionGroup[];
  contradictions?: ContradictionItem[];
  contradictions_summary?: string;
  unknowns?: string[];
  gaps_identified?: string[];
  citations?: Citation[];
  sources?: Source[];
  metadata?: {
    total_claims?: number;
    total_sources?: number;
    total_nodes?: number;
    total_edges?: number;
    /** Final coverage estimate; the only coverage signal for replayed sessions. */
    coverage?: number;
    /** Whether the executive summary came from the LLM or the rule-based fallback. */
    synthesis?: "llm" | "fallback";
    /** How many one-click re-syntheses this report has already had. */
    retry_count?: number;
    iterations_completed?: number;
    generated_at?: string;
  };
}

// ─── WebSocket message types ─────────────────────────────────────────────────

export type WSMessageType =
  | "initialized"
  | "search_started"
  | "sources_found"
  | "extraction_started"
  | "claims_extracted"
  | "knowledge_updated"
  | "facet_updated"
  | "ikf_updated"
  | "memory_recalled"
  | "memory_updated"
  | "contradiction_detected"
  | "decision_made"
  | "transition_recorded"
  | "rl_shadow"
  | "iteration_complete"
  | "synthesis_regenerated"
  | "completed"
  | "stopped"
  | "error";

/** One dimension of the research question and how much evidence it has. */
export interface FacetCoverageEntry {
  facet: string;
  claims: number;
  coverage: number;
  is_gap: boolean;
}

export interface WSMessage {
  type: WSMessageType;
  /** Per-session sequence stamped by the server; absent on unrecorded messages. */
  seq?: number;
  session_id?: string;
  status?: string;
  question?: string;
  iteration?: number;
  query?: string;
  count?: number;
  total_sources?: number;
  total_claims?: number;
  sources_count?: number;
  nodes?: number;
  edges?: number;
  severity?: string;
  action?: string;
  reasoning?: string;
  coverage?: number;
  information_gain?: number;
  stop_reason?: string;
  report_ready?: boolean;
  by?: string;
  message?: string;
  recoverable?: boolean;
  /** Model-call budget telemetry attached to iteration/ completion events. */
  llm_calls?: number;
  budget_calls?: number;
  context_chars?: number;
  context_budget_chars?: number;
  /** Dimension the current search is meant to fill (facet-directed search). */
  facet?: string;
  /** Per-dimension coverage snapshot streamed once per iteration. */
  facets?: FacetCoverageEntry[];
  facet_coverage?: number;
  facet_gaps?: string[];
  /** Synthesis mode reported by a re-synthesis event. */
  synthesis?: string;
  retry_count?: number;
  /** IKF 2.0 snapshot streamed once per iteration. */
  evidence?: EvidenceSummary;
  versions?: {
    groups?: number;
    single?: number;
    versioned?: number;
    conflicted?: number;
  };
  entities?: { entities?: number; aliases?: number; merges?: number };
  temporal_versions_suppressed?: number;
  /** V2 2.3 — persisted transition telemetry (transition_recorded). */
  transition_id?: string;
  reward?: number;
  reward_components?: Record<string, number>;
  state_hash?: string;
  state_bytes?: number;
  sources_added?: number;
  claims_added?: number;
  // ── V2 2.7 shadow comparison (rl_shadow + decision_made) ──
  policy_id?: string;
  policy_algorithm?: string;
  jev_action?: string;
  jev_reasoning?: string | null;
  jev_expected_value?: number | null;
  rl_action?: string;
  rl_expected_value?: number | null;
  rl_scores?: Record<string, number>;
  support?: number;
  fallback?: boolean;
  disagreement?: boolean;
  prediction_id?: string;
  state_key?: string;
  // ── V2 2.1 long-term memory ──
  items?: MemoryItemModel[];
  stored?: Record<string, number>;
  dead_ends_seeded?: number;
  entities_seeded?: number;
}

// ─── Persisted session events (replay) ───────────────────────────────────────

export interface SessionEvent {
  seq: number;
  type: string;
  iteration: number | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface SessionEventsResponse {
  session_id: string;
  total: number;
  latest_seq: number;
  events: SessionEvent[];
}

// ─── Activity log item ───────────────────────────────────────────────────────

export interface ActivityItem {
  id: string;
  timestamp: Date;
  type: WSMessageType;
  message: string;
  meta?: Record<string, unknown>;
  /** Sequence of the originating event, used to skip replayed duplicates. */
  seq?: number;
}

// ─── API Request types ───────────────────────────────────────────────────────

export interface StartResearchRequest {
  question: string;
  depth: DepthLevel;
  min_sources_required?: number;
  max_research_time_minutes?: number;
}

// ─── V2: formal research state and action space ──────────────────────────────

/**
 * The declared V2 action space. Only the first four are executable by the
 * orchestrator today; the rest share one vocabulary with a future executor and
 * are listed for completeness, never chosen by a live run.
 */
export type PolicyActionType =
  | "SEARCH"
  | "VERIFY"
  | "EXPAND_QUERY"
  | "STOP"
  | "SEARCH_NEW_FACET"
  | "SEARCH_PRIMARY_SOURCE"
  | "SEARCH_RECENT_SOURCE"
  | "SEARCH_COUNTER_EVIDENCE"
  | "COMPARE_SOURCES"
  | "REVISIT_WEAK_CLAIM";

/** Which policy produced a transition. Production runs are always "JEV". */
export type PolicySource = "JEV" | "RL_SHADOW" | "OTHER";

/**
 * The JSON-compatible research state stored with every transition.
 *
 * Mirrors `backend/app/services/rl/research_state.py`; IDs, aggregates and
 * compact summaries only, so a snapshot never carries raw source content.
 */
export interface ResearchStateSnapshot {
  session_id: string;
  question: string;
  iteration: number;
  depth: string;
  total_sources: number;
  total_claims: number;
  total_nodes: number;
  total_edges: number;
  information_gain: number;
  coverage: number;
  unresolved_contradictions: number;
  resolved_contradictions: number;
  unresolved_gaps: string[];
  facet_coverage: number;
  source_quality: number;
  source_diversity: number;
  confidence_distribution: { high?: number; medium?: number; low?: number };
  duplicate_count: number;
  time_elapsed: number;
  remaining_time: number;
  remaining_search_budget: number;
  remaining_llm_budget: number;
  max_iterations: number;
  previous_action: string | null;
  previous_reward: number | null;
  current_query: string | null;
  contradictions_are_new: boolean;
  plateau_iterations: number;
  llm_calls: number;
}

/** One named reason inside a stored reward, with its signed contribution. */
export interface RewardExplanationRow {
  component: string;
  value: number;
  reason: string;
  direction: "credit" | "debit";
}

/** A `state -> action -> observation -> reward -> next_state` step. */
export interface TransitionRecord {
  id: string;
  session_id: string;
  iteration: number;
  action_type: string;
  action_parameters: Record<string, unknown>;
  observation: Record<string, unknown>;
  reward: number;
  reward_components: Record<string, number>;
  information_gain: number;
  coverage_before: number;
  coverage_after: number;
  contradictions_before: number;
  contradictions_after: number;
  sources_added: number;
  claims_added: number;
  execution_time: number;
  policy_source: string;
  done: boolean;
  state_hash?: string | null;
  state_bytes: number;
  state_before: Partial<ResearchStateSnapshot>;
  state_after?: Partial<ResearchStateSnapshot> | null;
  created_at?: string | null;
}

export interface TrajectoryResponse {
  session_id: string;
  total: number;
  complete: boolean;
  total_reward: number;
  average_reward: number;
  policies: Record<string, number>;
  transitions: TransitionRecord[];
}

/** What the offline policy would have done, next to what JEV did. */
export interface ShadowPrediction {
  id: string;
  iteration: number;
  policy_id?: string | null;
  state_key: string;
  jev_action: string;
  jev_reasoning?: string | null;
  jev_expected_value?: number | null;
  rl_action: string;
  rl_expected_value?: number | null;
  rl_scores: Record<string, number>;
  rl_support: number;
  fallback: boolean;
  actual_reward?: number | null;
  estimated_rl_reward?: number | null;
  disagreement: boolean;
  created_at?: string | null;
}

export interface PredictionsResponse {
  session_id: string;
  total: number;
  agreements: number;
  disagreements: number;
  predictions: ShadowPrediction[];
}

/** One decision step: state, options, JEV choice, RL choice and the reward. */
export interface DecisionInspectorEntry {
  iteration: number;
  state: Partial<ResearchStateSnapshot>;
  state_key?: string | null;
  available_actions: string[];
  jev_action?: string | null;
  jev_reasoning: string;
  jev_expected_value?: number | null;
  rl_action?: string | null;
  rl_expected_value?: number | null;
  rl_scores: Record<string, number>;
  rl_support: number;
  disagreement: boolean;
  actual_action?: string | null;
  reward?: number | null;
  reward_components: Record<string, number>;
  reward_explanation: RewardExplanationRow[];
  information_gain?: number | null;
  coverage_after?: number | null;
  policy_source?: string | null;
}

export interface DecisionInspectorResponse {
  session_id: string;
  total: number;
  entries: DecisionInspectorEntry[];
}

export interface SessionStateResponse {
  session_id: string;
  state: ResearchStateSnapshot;
  state_hash: string;
  state_bytes: number;
  features: Record<string, string>;
  state_key: string;
  /** `trajectory` when read from the last recorded step, else `reconstructed`. */
  source: "trajectory" | "reconstructed";
  latest_prediction?: ShadowPrediction | null;
}

// ─── V2: offline dataset, policies and evaluation ────────────────────────────

export interface DatasetSample {
  state: Partial<ResearchStateSnapshot>;
  action: string;
  reward: number;
  next_state?: Partial<ResearchStateSnapshot> | null;
  done: boolean;
}

export interface DatasetIssue {
  kind: string;
  session_id: string;
  iteration: number;
  detail: string;
}

export interface DatasetStats {
  version: string;
  dataset_hash: string;
  transitions: number;
  sessions: number;
  session_ids: string[];
  actions: Record<string, number>;
  policy_sources: Record<string, number>;
  done_transitions: number;
  average_reward: number;
  total_reward: number;
  average_information_gain: number;
  average_steps_per_session: number;
  recorded_transitions?: number;
  sessions_with_transitions?: number;
  complete_sessions?: number;
  by_policy_source?: Record<string, number>;
  issues?: Record<string, number>;
  dropped: number;
}

export interface DatasetResponse {
  version: string;
  dataset_hash: string;
  transitions: number;
  sessions: number;
  session_ids: string[];
  actions: Record<string, number>;
  policy_sources: Record<string, number>;
  done_transitions: number;
  average_reward: number;
  total_reward: number;
  average_information_gain: number;
  average_steps_per_session: number;
  recorded_transitions?: number;
  sessions_with_transitions?: number;
  complete_sessions?: number;
  by_policy_source?: Record<string, number>;
  issues?: Record<string, number>;
  dropped: number;
  issues_list?: DatasetIssue[];
  samples: DatasetSample[];
}

export interface OfflinePolicy {
  id: string;
  name: string;
  version: string;
  algorithm: string;
  dataset_version?: string | null;
  dataset_hash?: string | null;
  baseline: string;
  samples: number;
  sessions: number;
  active: boolean;
  metrics: Record<string, unknown>;
  notes?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** What a backfill pass reconstructed from V1 history (decisions + actions). */
export interface BackfillResult {
  sessions_requested: number;
  sessions_backfilled: number;
  transitions_created: number;
  skipped: number;
  session_ids: string[];
}

export interface DatasetBuildResponse {
  dataset: DatasetStats;
  trained: boolean;
  policy?: OfflinePolicy | null;
  policy_metrics: Record<string, unknown>;
  backfill?: BackfillResult | null;
}

export interface PoliciesResponse {
  total: number;
  policies: OfflinePolicy[];
}

export interface EvaluationMetrics {
  policy: string;
  steps: number;
  observed_steps: number;
  counterfactual_steps: number;
  unestimable_steps: number;
  total_reward: number;
  average_reward: number;
  average_information_gain: number;
  coverage_improvement: number;
  average_iterations: number;
  duplicate_search_rate: number;
  contradiction_resolution_rate: number;
  stop_rate: number;
  unnecessary_action_rate: number;
  research_cost_seconds: number;
  time_to_convergence?: number | null;
  action_distribution: Record<string, number>;
  estimated: boolean;
}

export interface EvaluationActionRow {
  action: string;
  sample_size: number;
  observed_steps: number;
  counterfactual_steps: number;
  average_reward?: number | null;
  estimated: boolean;
  baseline_sample_size: number;
  baseline_average_reward?: number | null;
  reward_delta?: number | null;
}

export interface EvaluationSessionRow {
  session_id: string;
  steps: number;
  observed_steps: number;
  counterfactual_steps: number;
  average_reward?: number | null;
  total_reward: number;
  baseline_average_reward?: number | null;
  reward_delta?: number | null;
  final_coverage: number;
  stopped: boolean;
}

export interface EvaluationReport {
  run_id?: string | null;
  policy: string;
  baseline?: string | null;
  dataset_version: string;
  dataset_hash: string;
  dataset_size: number;
  sessions: string[];
  max_steps?: number | null;
  metrics: EvaluationMetrics;
  baseline_metrics?: EvaluationMetrics | null;
  comparison: Record<string, unknown>;
  per_session: EvaluationSessionRow[];
  per_action: EvaluationActionRow[];
  notes: string[];
}

export interface EvaluationRunSummary {
  id: string;
  policy: string;
  baseline?: string | null;
  dataset_version: string;
  dataset_hash?: string | null;
  dataset_size: number;
  sessions: number;
  max_steps?: number | null;
  status: string;
  aggregate: Record<string, unknown>;
  comparison: Record<string, unknown>;
  notes: string[];
  created_at?: string | null;
  completed_at?: string | null;
}

export interface EvaluationResultsResponse {
  total: number;
  runs: EvaluationRunSummary[];
}

export interface EvaluationResultDetail {
  id: string;
  policy: string;
  baseline?: string | null;
  dataset_version: string;
  dataset_hash?: string | null;
  dataset_size: number;
  sessions: number;
  max_steps?: number | null;
  status: string;
  config: Record<string, unknown>;
  aggregate: Record<string, unknown>;
  comparison: Record<string, unknown>;
  notes: string[];
  created_at?: string | null;
  completed_at?: string | null;
  results: Record<string, unknown>[];
}

export interface EvaluationRunRequest {
  policy: "jev" | "rl";
  baseline?: "jev" | "none";
  dataset_version?: string;
  max_steps?: number;
  session_ids?: string[];
  include_incomplete?: boolean;
  persist?: boolean;
}

// ─── V2: long-term memory ────────────────────────────────────────────────────

export interface MemoryItemModel {
  id: string;
  kind: string;
  key: string;
  text: string;
  payload: Record<string, unknown>;
  importance: number;
  confidence: number;
  hits: number;
  embedded: boolean;
  embedding_model?: string | null;
  source_session_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_used_at?: string | null;
  recall?: Record<string, number> | null;
}

export interface MemoryListResponse {
  total: number;
  items: MemoryItemModel[];
}

/** Where a remembered item came from — required for anything auditable. */
export interface MemoryProvenance {
  session_id?: string | null;
  learned_in_session?: string | null;
  created_at?: string | null;
  last_verified_at?: string | null;
  status?: string | null;
  sources: string[];
}

/** One observation of a remembered fact. */
export interface MemoryVersionEntry {
  value: string;
  text: string;
  valid_from?: number | null;
  valid_to?: number | null;
  precision: string;
  session_id?: string | null;
  claim_id?: string | null;
  sources: string[];
  confidence: number;
  recorded_at?: string | null;
  status: string;
}

export interface MemoryConflictItem {
  id: string;
  key: string;
  text: string;
  subject?: string | null;
  predicate?: string | null;
  status: string;
  conflicts: number;
  sources: string[];
  versions: MemoryVersionEntry[];
  confirmation_count: number;
  importance: number;
  confidence: number;
  provenance: MemoryProvenance;
}

export interface MemoryConflictsResponse {
  total: number;
  status_counts: Record<string, number>;
  items: MemoryConflictItem[];
}

export interface MemorySessionResponse {
  session_id: string;
  total: number;
  items: MemoryItemModel[];
}

export interface MemoryPromoteResponse {
  session_id: string;
  stored: Record<string, number>;
  updates: Record<string, number>;
  reason?: string | null;
}
