"use client";

import React, { useEffect, useMemo, useState } from "react";
import { explainReward } from "@/lib/reward-helpers";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Brain,
  FileJson,
  FileText,
  Network,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
} from "lucide-react";
import { ActivityFeed } from "@/components/ui/ActivityFeed";
import { KnowledgeGraphView } from "@/components/research/KnowledgeGraphView";
import { DashboardStats } from "@/components/research/DashboardStats";
import type { LiveStats } from "@/components/research/DashboardStats";
import { FacetCoveragePanel } from "@/components/research/FacetCoveragePanel";
import { ReportView } from "@/components/research/ReportView";
import { DecisionInspector } from "@/components/research/DecisionInspector";
import { StateInspector } from "@/lib/state-inspector";
import { SkeletonList } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  startResearch,
  stopResearch,
  getReport,
  retryReportSynthesis,
  getSessionState,
  getSessionTrajectory,
} from "@/lib/api";
import { latestFacetState } from "@/lib/facets";
import {
  loadSessionTimeline,
  mergeLiveActivity,
  mergeLiveMessages,
  timelineFromReport,
  type SessionTimeline,
} from "@/lib/timeline";
import type {
  ResearchSession,
  WSMessage,
  ActivityItem,
  ResearchReport,
  StartResearchRequest,
  ResearchStateSnapshot,
  ShadowPrediction,
  RewardExplanationRow,
} from "@/lib/types";

interface ResearchDashboardProps {
  session: ResearchSession;
  messages: WSMessage[];
  activity: ActivityItem[];
  isConnected: boolean;
  onReset: () => void;
  /** Launches another run (pending start or full restart) and opens it. */
  onStartSession: (session: ResearchSession) => void;
}

const TABS: {
  key: "activity" | "graph" | "report" | "decisions" | "state";
  label: string;
  Icon: React.ComponentType<{ size?: number }>;
}[] = [
  { key: "activity", label: "Activity log", Icon: Activity },
  { key: "graph", label: "Knowledge graph", Icon: Network },
  { key: "decisions", label: "Decisions", Icon: Brain },
  { key: "state", label: "State inspector", Icon: FileJson },
  { key: "report", label: "Research report", Icon: FileText },
];

export function ResearchDashboard({
  session,
  messages,
  activity,
  isConnected,
  onReset,
  onStartSession,
}: ResearchDashboardProps) {
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [activeTab, setActiveTab] = useState<"activity" | "report" | "graph" | "decisions" | "state">("activity");
  const [stopping, setStopping] = useState(false);
  const [userStopped, setUserStopped] = useState(false);
  const [relaunching, setRelaunching] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // V2 state inspector: formal research state + latest shadow prediction
  const [stateInspectorState, setStateInspectorState] = useState<ResearchStateSnapshot | null>(null);
  const [stateInspectorHash, setStateInspectorHash] = useState<string | null>(null);
  const [stateInspectorBytes, setStateInspectorBytes] = useState<number>(0);
  const [stateInspectorRewardComponents, setStateInspectorRewardComponents] = useState<Record<string, number>>({});
  const [stateInspectorRewardExplanation, setStateInspectorRewardExplanation] = useState<RewardExplanationRow[] | undefined>(undefined);
  const [stateInspectorTotalReward, setStateInspectorTotalReward] = useState<number | null>(null);
  const [stateInspectorPrediction, setStateInspectorPrediction] = useState<ShadowPrediction | undefined>(undefined);
  const [stateInspectorLoading, setStateInspectorLoading] = useState(true);
  const [stateInspectorError, setStateInspectorError] = useState<string | null>(null);
  // Stored event log, tagged with the session it belongs to so switching
  // sessions never shows the previous run's timeline.
  const [timeline, setTimeline] = useState<{
    sessionId: string;
    data: SessionTimeline;
  } | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  // Replay the stored event log. The live socket only carries what happens from
  // now on, so without this a finished investigation shows an empty activity log.
  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const stored = await loadSessionTimeline(session.id);
        if (!ignore) {
          setTimeline({ sessionId: session.id, data: stored });
          setTimelineError(null);
        }
      } catch {
        if (!ignore) {
          setTimelineError("Stored activity could not be loaded.");
        }
      }
    })();
    return () => {
      ignore = true;
    };
  }, [session.id]);

  // Refresh the formal state when the tab opens or the session changes.
  useEffect(() => {
    let ignored = false;
    (async () => {
      if (activeTab !== "state" && activeTab !== "decisions") return;
      setStateInspectorLoading(true);
      setStateInspectorError(null);
      try {
        const stateRes = await getSessionState(session.id);
        if (!ignored) {
          setStateInspectorState(stateRes.state as ResearchStateSnapshot);
          setStateInspectorHash(stateRes.state_hash);
          setStateInspectorBytes(stateRes.state_bytes);
          setStateInspectorTotalReward(null);
          setStateInspectorRewardComponents({});
          setStateInspectorRewardExplanation(undefined);
          setStateInspectorPrediction(stateRes.latest_prediction ?? undefined);
        }
        // Pull reward components + explanation from the last transition.
        try {
          const traj = await getSessionTrajectory(session.id, 1);
          if (!ignored && traj.transitions.length > 0) {
            const last = traj.transitions[traj.transitions.length - 1];
            setStateInspectorRewardComponents(last.reward_components ?? {});
            setStateInspectorTotalReward(last.reward);              setStateInspectorRewardExplanation(last.reward_components
              ? explainReward(last.reward_components)
              : undefined);
          }
        } catch {
          /* state is fine without trajectory */
        }
      } catch (err) {
        if (!ignored) setStateInspectorError(err instanceof Error ? err.message : "Could not load research state.");
      } finally {
        if (!ignored) setStateInspectorLoading(false);
      }
    })();
    return () => { ignored = true; };
  }, [session.id, activeTab]);

  const replay = timeline && timeline.sessionId === session.id ? timeline.data : null;
  const timelineLoading = !replay && !timelineError;

  // Sessions recorded before the event log existed still get a readable feed,
  // rebuilt from their saved report and clearly labelled as reconstructed.
  const replayed = useMemo<SessionTimeline | null>(() => {
    if (!replay) return null;
    if (replay.latestSeq === 0 && report?.metadata) return timelineFromReport(report);
    return replay;
  }, [replay, report]);
  const reconstructed = replayed !== null && replay !== null && replayed !== replay;
  const replayedMaxSeq = replay?.latestSeq ?? 0;

  const mergedMessages = useMemo(
    () => mergeLiveMessages(replay?.messages ?? [], messages, replayedMaxSeq),
    [replay, messages, replayedMaxSeq]
  );

  const feedItems = useMemo(
    () => mergeLiveActivity(replayed?.activity ?? [], activity, replayedMaxSeq),
    [replayed, activity, replayedMaxSeq]
  );

  // Newest facet snapshot, live or replayed: which dimensions of the question
  // the run has evidence for and which it is still working on.
  const facetState = useMemo(
    () => latestFacetState(mergedMessages),
    [mergedMessages]
  );

  // Derive live stats directly from WS messages
  const stats = useMemo<LiveStats>(() => {
    const s: LiveStats = {
      sources: session.total_sources || 0,
      claims: session.total_claims || 0,
      nodes: 0,
      edges: 0,
      coverage: 0,
      iteration: session.current_iteration || 0,
    };
    for (const msg of mergedMessages) {
      if (msg.total_sources !== undefined) s.sources = msg.total_sources;
      if (msg.total_claims !== undefined) s.claims = msg.total_claims;
      if (msg.nodes !== undefined) s.nodes = msg.nodes;
      if (msg.edges !== undefined) s.edges = msg.edges;
      if (msg.coverage !== undefined) s.coverage = msg.coverage;
      if (msg.iteration !== undefined) s.iteration = msg.iteration;
      if (msg.action) s.lastAction = msg.action;
      if (msg.reasoning) s.lastReasoning = msg.reasoning;
      if (msg.stop_reason) s.stopReason = msg.stop_reason;
      if (msg.llm_calls !== undefined) s.llmCalls = msg.llm_calls;
      if (msg.budget_calls !== undefined) s.budgetCalls = msg.budget_calls;
      if (msg.context_chars !== undefined) s.contextChars = msg.context_chars;
      if (msg.context_budget_chars !== undefined)
        s.contextBudget = msg.context_budget_chars;
    }

    // Sessions opened from history have no live stream, so fall back to the
    // persisted report rather than reporting zero coverage and zero entities
    // for an investigation that actually produced a knowledge graph.
    if (report?.metadata) {
      const meta = report.metadata;
      if (s.coverage === 0 && typeof meta.coverage === "number") {
        s.coverage = meta.coverage;
      }
      if (s.nodes === 0 && meta.total_nodes) s.nodes = meta.total_nodes;
      if (s.edges === 0 && meta.total_edges) s.edges = meta.total_edges;
    }

    return s;
  }, [
    mergedMessages,
    report,
    session.total_sources,
    session.total_claims,
    session.current_iteration,
  ]);

  // V2: the newest recorded transition, for live state-inspector refreshes.
  const latestTransition = useMemo<WSMessage | null>(() => {
    for (let i = mergedMessages.length - 1; i >= 0; i--) {
      if (mergedMessages[i].type === "transition_recorded") return mergedMessages[i];
    }
    return null;
  }, [mergedMessages]);

  // V2: the newest shadow prediction on the stream.
  const latestShadow = useMemo<WSMessage | null>(() => {
    for (let i = mergedMessages.length - 1; i >= 0; i--) {
      if (mergedMessages[i].type === "rl_shadow") return mergedMessages[i];
    }
    return null;
  }, [mergedMessages]);

  // Live transition/shadow telemetry for the inspector panels, derived during
  // render from the message stream (no setState needed). The state tab prefers
  // these live values over the ones fetched from the store.
  const liveInspector = useMemo(() => {
    const out: {
      stateHash?: string;
      totalReward?: number;
      components?: Record<string, number>;
      explanation?: RewardExplanationRow[];
      prediction?: ShadowPrediction;
    } = {};
    if (latestTransition) {
      const msg = latestTransition;
      if (msg.state_hash != null) out.stateHash = msg.state_hash;
      if (msg.reward != null) out.totalReward = msg.reward;
      if (msg.reward_components) {
        out.components = msg.reward_components as Record<string, number>;
        out.explanation = explainReward(msg.reward_components as Record<string, number>);
      }
    }
    if (latestShadow && latestShadow.state_key != null) {
      const msg = latestShadow;
      out.prediction = {
        id: msg.prediction_id ?? `live-${msg.iteration}`,
        iteration: msg.iteration ?? 0,
        state_key: msg.state_key,
        jev_action: msg.jev_action ?? "",
        jev_reasoning: msg.jev_reasoning ?? (msg.jev_action ? "" : undefined),
        jev_expected_value: msg.jev_expected_value,
        rl_action: msg.rl_action ?? "",
        rl_expected_value: msg.rl_expected_value,
        rl_scores: msg.rl_scores ?? {},
        rl_support: msg.support ?? 0,
        fallback: msg.fallback ?? false,
        disagreement: msg.disagreement ?? false,
      } as unknown as ShadowPrediction;
    }
    return out;
  }, [latestTransition, latestShadow]);

  // Derive current status directly
  const currentStatus = useMemo<string>(() => {
    if (userStopped) return "stopped";
    for (let i = mergedMessages.length - 1; i >= 0; i--) {
      const t = mergedMessages[i].type;
      if (t === "completed") return "completed";
      if (t === "stopped") return "stopped";
      if (t === "error") return "error";
      if (t === "initialized" || t === "search_started") return "running";
    }
    return session.status;
  }, [mergedMessages, session.status, userStopped]);

  // Auto-fetch the report once the session completes. State updates happen after
  // the await, so the fetch never re-enters the effect; failures land in
  // reportError and are retried explicitly by the user.
  useEffect(() => {
    if (currentStatus !== "completed" || report) return;
    let ignore = false;
    (async () => {
      try {
        const fetched = await getReport(session.id);
        if (!ignore) {
          setReport(fetched);
          setActiveTab("report");
        }
      } catch {
        if (!ignore) {
          setReportError(
            "The report could not be loaded — the backend may be offline or still generating it."
          );
        }
      }
    })();
    return () => {
      ignore = true;
    };
  }, [currentStatus, report, session.id, loadAttempt]);

  const reportPending = currentStatus === "completed" && !report && !reportError;

  const retryReportLoad = () => {
    setReportError(null);
    setLoadAttempt((attempt) => attempt + 1);
  };

  // Re-synthesising only re-runs the summary step, so the report object is
  // replaced in place rather than triggering a new research run.
  const handleRetrySynthesis = async () => {
    const regenerated = await retryReportSynthesis(session.id);
    setReport(regenerated);
  };

  const handleStop = async () => {
    if (stopping) return;
    setStopping(true);
    setActionError(null);
    try {
      await stopResearch(session.id);
      setUserStopped(true);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Could not stop the research session."
      );
    } finally {
      setStopping(false);
    }
  };

  // The API can only start a run (no resume endpoint), so both "start" and
  // "restart" relaunch the same question as a fresh session and switch to it.
  const handleLaunchAgain = async () => {
    if (relaunching) return;
    setRelaunching(true);
    setActionError(null);
    try {
      const clampMinutes = (value?: number) =>
        Math.min(10, Math.max(1, value ?? 8));
      const body: StartResearchRequest = {
        question: session.question,
        depth: session.depth,
        min_sources_required: session.min_sources_required,
        max_research_time_minutes: clampMinutes(session.max_research_time_minutes),
      };
      const next = await startResearch(body);
      onStartSession(next);
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : "Could not start the research run. Is the backend running?"
      );
    } finally {
      setRelaunching(false);
    }
  };

  // Iteration cap comes from the backend depth profile; the local map is only a
  // fallback for older session payloads that predate the max_iterations field.
  const fallbackIterations =
    session.depth === "shallow" ? 3 : session.depth === "standard" ? 5 : 8;
  const maxIterations = session.max_iterations ?? fallbackIterations;

  const status = currentStatus as ResearchSession["status"];
  const isRunning = status === "running" || status === "initializing";
  const isPending = status === "pending";
  const isDone = ["completed", "stopped", "error"].includes(status);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 20,
        width: "100%",
        maxWidth: 900,
      }}
    >
      {/* Session header */}
      <div
        className="card"
        style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 12 }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ flex: 1, minWidth: 260 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 6,
                flexWrap: "wrap",
              }}
            >
              <StatusBadge status={status} />
              {isConnected && isRunning && (
                <span
                  style={{
                    fontSize: "0.72rem",
                    color: "var(--info)",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    fontWeight: 600,
                  }}
                >
                  <span className="live-dot" aria-hidden="true" />
                  Live
                </span>
              )}
              <span className="badge badge-gray" style={{ fontSize: "0.68rem" }}>
                {session.depth.toUpperCase()}
              </span>
            </div>
            <h2
              style={{
                fontSize: "1rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                lineHeight: 1.4,
                wordBreak: "break-word",
              }}
            >
              {session.question}
            </h2>
          </div>

          {/* flexShrink must stay allowed: with a fixed basis this row cannot
              narrow at 375px, so the whole card (and the document) scrolled
              sideways instead of the buttons wrapping onto a second line. */}
          <div
            style={{
              display: "flex",
              gap: 8,
              flexShrink: 1,
              minWidth: 0,
              flexWrap: "wrap",
            }}
          >
            {isRunning && (
              <button
                className="btn-secondary"
                onClick={handleStop}
                disabled={stopping}
                style={{ padding: "8px 14px", fontSize: "0.8rem" }}
              >
                <Square size={13} aria-hidden="true" />
                {stopping ? "Stopping…" : "Stop research"}
              </button>
            )}

            {isPending && (
              <button
                className="btn-glow"
                onClick={handleLaunchAgain}
                disabled={relaunching}
                title="This run never started — launch it now with the same question and depth."
                style={{
                  padding: "8px 14px",
                  fontSize: "0.8rem",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <Play size={14} aria-hidden="true" />
                {relaunching ? "Starting…" : "Start pending research"}
              </button>
            )}

            {isDone && (
              <button
                className="btn-secondary"
                onClick={handleLaunchAgain}
                disabled={relaunching}
                title="Re-runs the same question from the first iteration as a new session."
                style={{ padding: "8px 14px", fontSize: "0.8rem" }}
              >
                <RotateCcw size={13} aria-hidden="true" />
                {relaunching ? "Restarting…" : "Restart from the beginning"}
              </button>
            )}

            {isDone && (
              <button
                className="btn-secondary"
                onClick={onReset}
                style={{ padding: "8px 14px", fontSize: "0.8rem" }}
              >
                <ArrowLeft size={13} aria-hidden="true" />
                New research
              </button>
            )}
          </div>
        </div>

        {isPending && !actionError && (
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            This session is queued but never ran. Starting it launches the same
            question from the first iteration as a new run.
          </p>
        )}

        {actionError && (
          <p
            style={{
              fontSize: "0.78rem",
              color: "var(--danger)",
              background: "var(--danger-soft)",
              border: "1px solid var(--danger-border)",
              borderRadius: 8,
              padding: "8px 12px",
              display: "flex",
              gap: 6,
              alignItems: "flex-start",
            }}
          >
            <AlertTriangle size={14} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
            {actionError}
          </p>
        )}

        <DashboardStats
          stats={stats}
          maxIterations={maxIterations}
          status={status}
          isDone={isDone}
          coverageKnown={stats.coverage > 0}
        />

        <FacetCoveragePanel state={facetState} />
      </div>

      {/* Tabs */}
      <div>
        <div
          role="tablist"
          aria-label="Session views"
          className="tablist"
          style={{
            display: "flex",
            gap: 4,
            borderBottom: "1px solid var(--border)",
            marginBottom: 12,
          }}
        >
          {TABS.map(({ key, label, Icon }) => {
            const active = activeTab === key;
            return (
              <button
                key={key}
                role="tab"
                id={`tab-${key}`}
                aria-selected={active}
                aria-controls={`panel-${key}`}
                onClick={() => setActiveTab(key)}
                className="tab-button"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  padding: "8px 16px",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  border: "none",
                  background: "none",
                  cursor: "pointer",
                  color: active ? "var(--accent-ink)" : "var(--text-muted)",
                  borderBottom: active
                    ? "2px solid var(--accent)"
                    : "2px solid transparent",
                }}
              >
                <Icon size={15} aria-hidden="true" />
                {label}
                {key === "report" && currentStatus === "completed" && (
                  <span className="badge badge-green" style={{ fontSize: "0.65rem" }}>
                    Ready
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {activeTab === "activity" && (
          <div
            role="tabpanel"
            id="panel-activity"
            aria-labelledby="tab-activity"
            className="card scroll-panel"
            style={{ padding: "12px 16px", maxHeight: 380 }}
          >
            <div
              style={{
                fontSize: "0.7rem",
                color: "var(--text-muted)",
                paddingBottom: 8,
                marginBottom: 8,
                borderBottom: "1px solid var(--border)",
              }}
            >
              {timelineLoading
                ? "Loading stored timeline…"
                : timelineError
                ? `${timelineError} Showing live updates only.`
                : reconstructed
                ? `Reconstructed from the saved report (${replayed?.activity.length ?? 0} entries) — this run predates stored event history.`
                : replayed && replayed.latestSeq > 0
                ? `Replayed ${replayed.activity.length} stored events from this session's log${isConnected ? ", live updates appended below" : ""}.`
                : "No stored events for this session yet — entries appear as the run progresses."}
            </div>
            {timelineLoading ? (
              <SkeletonList rows={4} height={40} lines={1} />
            ) : (
              <ActivityFeed items={feedItems} />
            )}
          </div>
        )}

        {activeTab === "graph" && (
          <div role="tabpanel" id="panel-graph" aria-labelledby="tab-graph">
            <KnowledgeGraphView sessionId={session.id} />
          </div>
        )}

        {activeTab === "decisions" && (
          <div role="tabpanel" id="panel-decisions" aria-labelledby="tab-decisions">
            <DecisionInspector sessionId={session.id} />
          </div>
        )}

        {activeTab === "state" && (
          <div role="tabpanel" id="panel-state" aria-labelledby="tab-state">
            {stateInspectorLoading ? (
              <SkeletonList rows={2} height={120} lines={1} />
            ) : stateInspectorError ? (
              <div style={{ padding: 20, textAlign: "center", color: "var(--danger)", fontSize: "0.85rem" }}>
                {stateInspectorError}
              </div>
            ) : (
              <StateInspector
                state={stateInspectorState}
                stateHash={liveInspector.stateHash ?? stateInspectorHash}
                stateBytes={stateInspectorBytes}
                rewardComponents={liveInspector.components ?? stateInspectorRewardComponents}
                rewardExplanation={liveInspector.explanation ?? stateInspectorRewardExplanation}
                totalReward={liveInspector.totalReward ?? stateInspectorTotalReward}
                latestPrediction={liveInspector.prediction ?? stateInspectorPrediction}
              />
            )}
          </div>
        )}

        {activeTab === "report" && (
          <div role="tabpanel" id="panel-report" aria-labelledby="tab-report">
            {reportPending && (
              <div
                className="card shimmer"
                style={{ height: 200, borderRadius: 16 }}
              />
            )}
            {!reportPending && !report && !reportError && (
              <div
                className="card"
                style={{
                  padding: 32,
                  textAlign: "center",
                  color: "var(--text-muted)",
                  fontSize: "0.9rem",
                }}
              >
                {isDone && status !== "completed"
                  ? "Research was stopped before a report was generated."
                  : "Report will be available once research completes."}
              </div>
            )}
            {reportError && !report && (
              <div
                className="card"
                style={{
                  padding: 32,
                  textAlign: "center",
                  fontSize: "0.9rem",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <span
                  style={{
                    color: "var(--danger)",
                    display: "flex",
                    gap: 6,
                    alignItems: "flex-start",
                  }}
                >
                  <AlertTriangle size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
                  {reportError}
                </span>
                <button
                  className="btn-secondary"
                  onClick={retryReportLoad}
                  style={{ padding: "8px 16px", fontSize: "0.82rem" }}
                >
                  <RefreshCw size={13} aria-hidden="true" />
                  Retry
                </button>
              </div>
            )}
            {report && (
              <ReportView
                report={report}
                onRetrySynthesis={handleRetrySynthesis}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
