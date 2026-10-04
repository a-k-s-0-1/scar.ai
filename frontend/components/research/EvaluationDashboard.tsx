"use client";

import React, { useEffect, useState } from "react";
import {
  Database,
  Brain,
  GitCompare,
  Play,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Hash,
  TrendingUp,
  AlertCircle,
} from "lucide-react";
import {
  getDatasetStats,
  buildDataset,
  runEvaluation,
  listEvaluationResults,
  listPolicies,
  activatePolicy,
  getRewardFormula,
} from "@/lib/api";
import type {
  DatasetStats,
  OfflinePolicy,
  EvaluationReport,
  EvaluationRunSummary,
} from "@/lib/types";

interface EvaluationDashboardProps {
  className?: string;
}

type Section = "dataset" | "policies" | "runs" | "run-wizard";

type PolicyChoice = "jev" | "rl";
type BaselineChoice = "jev" | "none";

function pct(value: number): string {
  return (value * 100).toFixed(1) + "%";
}

function signed(value: number | null | undefined): string {
  if (value == null) return "—";
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

function rewardColor(value: number | null | undefined): string {
  if (value == null) return "var(--text-muted)";
  return value > 0 ? "var(--ok)" : value < 0 ? "var(--danger)" : "var(--text-primary)";
}

function expandLabel(collapsed: boolean) {
  return collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />;
}

export function EvaluationDashboard({ className = "" }: EvaluationDashboardProps) {
  const [section, setSection] = useState<Section>("dataset");
  const [datasetStats, setDatasetStats] = useState<DatasetStats | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(true);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [backfillNote, setBackfillNote] = useState<string | null>(null);
  const [formulas, setFormulas] = useState<{ reward: Record<string, unknown>; actions: { executable: string[]; all: Record<string, unknown>[] }; dataset_version: string } | null>(null);

  const [policies, setPolicies] = useState<OfflinePolicy[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(true);

  const [runs, setRuns] = useState<EvaluationRunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);

  const [report, setReport] = useState<EvaluationReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  const [wizardPolicy, setWizardPolicy] = useState<PolicyChoice>("rl");
  const [wizardBaseline, setWizardBaseline] = useState<BaselineChoice>("jev");
  const [wizardMaxSteps, setWizardMaxSteps] = useState<number | "">(50);
  const [wizardSessionIds, setWizardSessionIds] = useState<string>("");
  const [wizardIncomplete, setWizardIncomplete] = useState(false);
  const [wizardPersist, setWizardPersist] = useState(true);
  const [wizardRunning, setWizardRunning] = useState(false);

  const [detailOpen, setDetailOpen] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        setDatasetLoading(true);
        setDatasetError(null);
        const stats = await getDatasetStats();
        if (!ignore) setDatasetStats(stats);
        const form = await getRewardFormula();
        if (!ignore) setFormulas(form);
      } catch (err) {
        if (!ignore) setDatasetError(err instanceof Error ? err.message : "Could not load dataset stats.");
      } finally {
        if (!ignore) setDatasetLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        setPoliciesLoading(true);
        const res = await listPolicies();
        if (!ignore) setPolicies(res.policies);
      } catch {
        /* leave policies empty */
      } finally {
        if (!ignore) setPoliciesLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        setRunsLoading(true);
        const res = await listEvaluationResults(20);
        if (!ignore) setRuns(res.runs);
      } catch {
        /* leave runs empty */
      } finally {
        if (!ignore) setRunsLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  const refreshPolicies = async () => {
    try {
      const res = await listPolicies();
      setPolicies(res.policies);
    } catch {
      /* ignore */
    }
  };

  const refreshRuns = async () => {
    try {
      const res = await listEvaluationResults(20);
      setRuns(res.runs);
    } catch {
      /* ignore */
    }
  };

  const runWizard = async () => {
    setReportError(null);
    setReport(null);
    setReportLoading(true);
    setWizardRunning(true);
    try {
      const body: Parameters<typeof runEvaluation>[0] = {
        policy: wizardPolicy,
        baseline: wizardBaseline,
        max_steps: wizardMaxSteps == null || wizardMaxSteps === "" ? undefined : Math.min(200, Math.max(1, wizardMaxSteps)),
        session_ids: wizardSessionIds.trim() ? wizardSessionIds.trim().split(",").map((s) => s.trim()).filter(Boolean) : undefined,
        include_incomplete: wizardIncomplete,
        persist: wizardPersist,
      };
      const result = await runEvaluation(body);
      setReport(result);
    } catch (err) {
      setReportError(err instanceof Error ? err.message : "Could not run evaluation.");
    } finally {
      setReportLoading(false);
      setWizardRunning(false);
    }
  };

  const runBuildAndTrain = async (activate: boolean) => {
    try {
      setDatasetLoading(true);
      setDatasetError(null);
      const result = await buildDataset({ train: true, activate, backfill: true });
      if (result.policy) {
        const updated = await listPolicies();
        setPolicies(updated.policies);
      }
      setDatasetStats(result.dataset);
      const bf = result.backfill;
      setBackfillNote(
        bf && bf.transitions_created > 0
          ? `Backfilled ${bf.transitions_created} transition(s) from ${bf.sessions_backfilled} past session(s) into the dataset.`
          : null
      );
    } catch (err) {
      setDatasetError(err instanceof Error ? err.message : "Could not build dataset.");
    } finally {
      setDatasetLoading(false);
    }
  };

  const activatePolicyById = async (policyId: string) => {
    try {
      await activatePolicy(policyId);
      await refreshPolicies();
    } catch (err) {
      setDatasetError(err instanceof Error ? err.message : "Could not activate policy.");
    }
  };

  const collapsedSections: Record<string, boolean> = {
    dataset: false,
    policies: false,
    runs: false,
    "run-wizard": false,
  };

  const toggleSection = (key: string) => {
    setDetailOpen((prev) => (prev === key ? null : key));
  };

  return (
    <div className={`card ${className}`} style={{ padding: "18px 20px", maxWidth: 900 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <GitCompare size={18} style={{ color: "var(--chart-2)" }} aria-hidden="true" />
        <span style={{ fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
          RL Evaluation Dashboard
        </span>
        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "auto" }}>
          JEV controls the live loop · RL learns offline
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
        {(["dataset", "policies", "runs", "run-wizard"] as Section[]).map((s) => (
          <button
            key={s}
            type="button"
            className={`btn-secondary${section === s ? " btn-active" : ""}`}
            onClick={() => setSection(s)}
            style={{ padding: "6px 12px", fontSize: "0.8rem" }}
          >
            {s === "dataset" && <Database size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {s === "policies" && <Brain size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {s === "runs" && <GitCompare size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {s === "run-wizard" && <Play size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {s === "dataset" && "Dataset"}
            {s === "policies" && "Policies"}
            {s === "runs" && "Runs"}
            {s === "run-wizard" && "Run evaluation"}
          </button>
        ))}
      </div>

      {datasetError && (
        <div style={{ padding: "10px 12px", background: "var(--danger-soft)", border: "1px solid var(--danger-border)", borderRadius: 8, marginBottom: 14, fontSize: "0.8rem", color: "var(--danger)" }}>
          <AlertCircle size={13} style={{ marginRight: 6 }} aria-hidden="true" />
          {datasetError}
        </div>
      )}

      {backfillNote && !datasetError && (
        <div style={{ padding: "8px 12px", background: "var(--ok-soft)", borderRadius: 8, marginBottom: 14, fontSize: "0.8rem", color: "var(--ok)" }}>
          {backfillNote}
        </div>
      )}

      {/* ── dataset section ── */}
      {section === "dataset" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button
              type="button"
              onClick={() => toggleSection("dataset")}
              style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 600 }}
            >
              {expandLabel(collapsedSections["dataset"])}
              Dataset
            </button>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              {datasetLoading ? (
                <RefreshCw size={14} className="spin" style={{ color: "var(--text-muted)" }} aria-hidden="true" />
              ) : (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={runBuildAndTrain.bind(null, true)}
                  style={{ padding: "4px 10px", fontSize: "0.78rem" }}
                >
                  <RefreshCw size={12} style={{ marginRight: 4 }} aria-hidden="true" />
                  Rebuild + train
                </button>
              )}
            </div>
          </div>

          {collapsedSections["dataset"] && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0 8px" }}>
              {datasetStats ? (
                <>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                    <StatCard label="Transitions" value={String(datasetStats.transitions)} sub={`${datasetStats.sessions} session(s)`} />
                    <StatCard label="Session IDs" value={String(datasetStats.session_ids?.length ?? datasetStats.sessions)} sub="included" />
                    <StatCard label="Average reward" value={datasetStats.average_reward.toFixed(3)} sub={signed(datasetStats.total_reward) + " total"} color={rewardColor(datasetStats.average_reward)} />
                    <StatCard label="Avg info gain" value={pct(datasetStats.average_information_gain)} sub="per transition" />
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <div className="card" style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8 }}>
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>Action distribution</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {Object.entries(datasetStats.actions ?? {}).sort((a, b) => b[1] - a[1]).map(([action, count]) => (
                          <div key={action} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <span style={{ width: 90, fontWeight: 600, fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>{action}</span>
                            <div style={{ flex: 1, height: 6, background: "var(--border)", borderRadius: 4, overflow: "hidden" }}>
                              <div style={{ width: `${(count / Math.max(...Object.values(datasetStats.actions ?? {}), 1)) * 100}%`, height: "100%", background: "var(--accent)", borderRadius: 4 }} />
                            </div>
                            <span style={{ fontVariantNumeric: "tabular-nums", fontSize: "0.75rem", color: "var(--text-muted)", width: 36, textAlign: "right" }}>{count}</span>
                          </div>
                        ))}
                        {Object.keys(datasetStats.actions ?? {}).length === 0 && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>No transitions yet.</div>}
                      </div>
                    </div>

                    <div className="card" style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8 }}>
                      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>Policy sources</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                        {Object.entries(datasetStats.policy_sources ?? {}).sort((a, b) => b[1] - a[1]).map(([source, count]) => (
                          <div key={source} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: "0.8rem" }}>
                            <span style={{ width: 90, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>{source}</span>
                            <div style={{ flex: 1, height: 6, background: "var(--border)", borderRadius: 4, overflow: "hidden" }}>
                              <div style={{ width: `${(count / Math.max(...Object.values(datasetStats.policy_sources ?? {}), 1)) * 100}%`, height: "100%", background: source === "JEV" ? "var(--accent)" : "var(--chart-2)", borderRadius: 4 }} />
                            </div>
                            <span style={{ fontVariantNumeric: "tabular-nums", fontSize: "0.75rem", color: "var(--text-muted)", width: 36, textAlign: "right" }}>{count}</span>
                          </div>
                        ))}
                        {Object.keys(datasetStats.policy_sources ?? {}).length === 0 && <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>No transitions yet.</div>}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Dataset</div>
                    <div style={{ display: "flex", gap: 16, fontSize: "0.8rem" }}>
                      <span>Version <span style={{ fontFamily: "ui-monospace, monospace", color: "var(--text-primary)" }}>{datasetStats.version ?? formulas?.dataset_version ?? "?"}</span></span>
                      <span>Hash <span style={{ fontFamily: "ui-monospace, monospace", color: "var(--text-secondary)", fontSize: "0.75rem" }}>{datasetStats.dataset_hash ?? "—"}</span></span>
                      <span>Transitions <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{datasetStats.transitions}</span></span>
                      <span>Dropped <span style={{ fontVariantNumeric: "tabular-nums", color: datasetStats.dropped ? "var(--warn)" : "var(--text-muted)" }}>{datasetStats.dropped}</span></span>
                    </div>
                  </div>
                </>
              ) : (
                <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  {datasetLoading ? "Loading dataset stats…" : "No dataset available yet."}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── policies section ── */}
      {section === "policies" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button
              type="button"
              onClick={() => toggleSection("policies")}
              style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 600 }}
            >
              {expandLabel(collapsedSections["policies"])}
              Policies
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={refreshPolicies}
              disabled={policiesLoading}
              style={{ padding: "4px 10px", fontSize: "0.78rem" }}
            >
              <RefreshCw size={12} style={{ marginRight: 4 }} className={policiesLoading ? "spin" : ""} aria-hidden="true" />
              Refresh
            </button>
          </div>

          {collapsedSections["policies"] && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0 8px" }}>
              {policiesLoading ? (
                <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>Loading policies…</div>
              ) : policies.length === 0 ? (
                <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  No policies trained yet. Train one from the dataset above.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {policies.map((policy) => (
                    <div
                      key={policy.id}
                      className="card"
                      style={{ padding: "12px 14px", background: policy.active ? "var(--ok-soft)" : "var(--bg-subtle)", borderRadius: 8, border: policy.active ? "1px solid var(--ok-border)" : "1px solid var(--border)" }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        {policy.active && <span className="badge badge-green" style={{ fontSize: "0.65rem" }}>active</span>}
                        <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{policy.name}</span>
                        <span style={{ marginLeft: "auto", fontSize: "0.72rem", fontFamily: "ui-monospace, monospace", color: "var(--text-muted)" }}>
                          {policy.algorithm}
                        </span>
                      </div>
                      <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                        <span>Samples: <strong style={{ color: "var(--text-primary)" }}>{policy.samples}</strong></span>
                        <span>Sessions: <strong style={{ color: "var(--text-primary)" }}>{policy.sessions}</strong></span>
                        <span>Baseline: <strong style={{ color: "var(--text-primary)" }}>{policy.baseline}</strong></span>
                        {policy.metrics && Object.keys(policy.metrics).length > 0 && (
                          <span style={{ color: "var(--text-muted)" }}>metrics: {Object.keys(policy.metrics).length} keys</span>
                        )}
                      </div>
                      {!policy.active && (
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ marginTop: 8, padding: "3px 10px", fontSize: "0.75rem" }}
                          onClick={() => activatePolicyById(policy.id)}
                        >
                          Activate
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── runs section ── */}
      {section === "runs" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button
              type="button"
              onClick={() => toggleSection("runs")}
              style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 600 }}
            >
              {expandLabel(collapsedSections["runs"])}
              Evaluation runs
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={refreshRuns}
              disabled={runsLoading}
              style={{ padding: "4px 10px", fontSize: "0.78rem" }}
            >
              <RefreshCw size={12} style={{ marginRight: 4 }} className={runsLoading ? "spin" : ""} aria-hidden="true" />
              Refresh
            </button>
          </div>

          {collapsedSections["runs"] && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, padding: "4px 0 8px" }}>
              {runsLoading ? (
                <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>Loading runs…</div>
              ) : runs.length === 0 ? (
                <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  No evaluation runs yet. Use the Run evaluation wizard to compare policies on the dataset.
                </div>
              ) : (
                runs.map((run) => (
                  <div
                    key={run.id}
                    className="card"
                    style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8 }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <Hash size={13} style={{ color: "var(--text-muted)" }} aria-hidden="true" />
                      <span style={{ fontWeight: 700, fontSize: "0.82rem" }}>{run.policy.toUpperCase()}</span>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.72rem" }}>vs {run.baseline ?? "—"}</span>
                      <span className="badge" style={{ background: "var(--border)", color: "var(--text-muted)", fontSize: "0.65rem" }}>
                        {run.status}
                      </span>
                      {run.status === "completed" && (
                        <span className="badge badge-green" style={{ fontSize: "0.65rem" }}>completed</span>
                      )}
                      <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                        {(run.completed_at ?? run.created_at) ?? ""}
                      </span>
                    </div>
                    <div style={{ display: "flex", gap: 18, marginTop: 8, fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                      <span>Dataset: <strong style={{ color: "var(--text-primary)" }}>{run.dataset_size}</strong> transitions</span>
                      <span>Sessions: <strong style={{ color: "var(--text-primary)" }}>{run.sessions}</strong></span>
                      {run.max_steps != null && <span>Max steps: <strong style={{ color: "var(--text-primary)" }}>{run.max_steps}</strong></span>}
                      <span style={{ color: "var(--text-muted)", fontSize: "0.72rem", fontFamily: "ui-monospace, monospace" }}>{run.id.slice(0, 8)}</span>
                    </div>
                    <div style={{ display: "flex", gap: 14, marginTop: 6, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ padding: "2px 8px", fontSize: "0.72rem" }}
                        onClick={() => setDetailOpen(detailOpen === run.id ? null : run.id)}
                      >
                        {detailOpen === run.id ? <><ChevronUp size={12} style={{ marginRight: 4 }} />Hide</> : <><ChevronDown size={12} style={{ marginRight: 4 }} />Details</>}
                      </button>
                    </div>
                    {detailOpen === run.id && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 6, fontSize: "0.78rem" }}>
                        {run.aggregate && Object.keys(run.aggregate).length > 0 && (
                          <div><span style={{ color: "var(--text-muted)" }}>Aggregate:</span>{" "}<code style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.72rem" }}>{JSON.stringify(run.aggregate)}</code></div>
                        )}
                        {run.comparison && Object.keys(run.comparison).length > 0 && (
                          <div><span style={{ color: "var(--text-muted)" }}>Comparison:</span>{" "}<code style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.72rem" }}>{JSON.stringify(run.comparison)}</code></div>
                        )}
                        {run.notes && run.notes.length > 0 && (
                          <div><span style={{ color: "var(--text-muted)" }}>Notes:</span>{" "}
                            {run.notes.map((n, i) => <span key={i}>{n}{i < run.notes!.length - 1 ? " · " : ""}</span>)}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* ── run wizard section ── */}
      {section === "run-wizard" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <button
              type="button"
              onClick={() => toggleSection("run-wizard")}
              style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 600 }}
            >
              {expandLabel(collapsedSections["run-wizard"])}
              Run evaluation
            </button>
          </div>

          {collapsedSections["run-wizard"] && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "4px 0 8px" }}>
              <div style={{ padding: "14px 16px", background: "var(--bg-subtle)", borderRadius: 8, fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                Replay the dataset through the chosen policy offline. Nothing here executes in a live run.
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Policy to evaluate
                  </label>
                  <div style={{ display: "flex", gap: 6 }}>
                    {(["jev", "rl"] as PolicyChoice[]).map((p) => (
                      <button
                        key={p}
                        type="button"
                        className={`btn-secondary${wizardPolicy === p ? " btn-active" : ""}`}
                        onClick={() => setWizardPolicy(p)}
                        style={{ padding: "5px 10px", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.04em" }}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Baseline comparison
                  </label>
                  <div style={{ display: "flex", gap: 6 }}>
                    {(["jev", "none"] as BaselineChoice[]).map((b) => (
                      <button
                        key={b}
                        type="button"
                        className={`btn-secondary${wizardBaseline === b ? " btn-active" : ""}`}
                        onClick={() => setWizardBaseline(b)}
                        style={{ padding: "5px 10px", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.04em" }}
                      >
                        {b}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Max steps per session
                  </label>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={wizardMaxSteps}
                    onChange={(e) => setWizardMaxSteps(e.target.value === "" ? "" : Number(e.target.value))}
                    style={{ width: "100%", padding: "6px 10px", border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-subtle)", color: "var(--text-primary)", fontSize: "0.82rem" }}
                    placeholder="50"
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Optional session IDs (comma separated)
                  </label>
                  <input
                    type="text"
                    value={wizardSessionIds}
                    onChange={(e) => setWizardSessionIds(e.target.value)}
                    style={{ width: "100%", padding: "6px 10px", border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg-subtle)", color: "var(--text-primary)", fontSize: "0.82rem" }}
                    placeholder="optional — leave blank for all sessions"
                  />
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem" }}>
                    <input
                      type="checkbox"
                      checked={wizardIncomplete}
                      onChange={(e) => setWizardIncomplete(e.target.checked)}
                      style={{ width: 16, height: 16, accentColor: "var(--accent)" }}
                    />
                    Include incomplete sessions
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: "0.82rem" }}>
                    <input
                      type="checkbox"
                      checked={wizardPersist}
                      onChange={(e) => setWizardPersist(e.target.checked)}
                      style={{ width: 16, height: 16, accentColor: "var(--accent)" }}
                    />
                    Persist run to history
                  </label>
                </div>

                <div style={{ alignSelf: "end" }}>
                  <button
                    type="button"
                    className="btn-glow"
                    onClick={runWizard}
                    disabled={wizardRunning}
                    style={{ padding: "8px 18px", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: 6 }}
                  >
                    {wizardRunning ? (
                      <><RefreshCw size={14} className="spin" aria-hidden="true" />Running…</>
                    ) : (
                      <><Play size={14} aria-hidden="true" />Run evaluation</>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── evaluation report ── */}
      {report && !reportLoading && !reportError && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginTop: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <TrendingUp size={15} style={{ color: "var(--chart-2)" }} aria-hidden="true" />
            <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)", letterSpacing: "0.02em" }}>
              Evaluation report
            </span>
            <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "var(--text-muted)" }}>
              {report.policy.toUpperCase()} vs {report.baseline ?? "—"}
            </span>
          </div>

          {report.notes && report.notes.length > 0 && (
            <div style={{ padding: "8px 10px", background: "var(--warn-soft)", borderRadius: 6, fontSize: "0.78rem", color: "var(--warn)", marginBottom: 12 }}>
              {report.notes.map((n, i) => <div key={i}>{n}</div>)}
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
            <ComparisonCard label="JEV avg reward" value={report.baseline_metrics?.average_reward ?? report.metrics.average_reward} color={rewardColor(report.baseline_metrics?.average_reward ?? report.metrics.average_reward)} />
            <ComparisonCard label="RL avg reward" value={report.metrics.average_reward} color={rewardColor(report.metrics.average_reward)} />
            <ComparisonCard label="JEV total reward" value={report.baseline_metrics?.total_reward ?? report.metrics.total_reward} color="var(--text-secondary)" />
            <ComparisonCard label="RL total reward" value={report.metrics.total_reward} color="var(--text-secondary)" />
          </div>

          {report.baseline_metrics && report.metrics && (
            <ComparisonCard
              label="Reward delta (RL − JEV)"
              value={report.metrics.average_reward - report.baseline_metrics.average_reward}
              color={report.metrics.average_reward - report.baseline_metrics.average_reward >= 0 ? "var(--ok)" : "var(--danger)"}
            />
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                Per-session breakdown
              </div>
              <div style={{ overflow: "auto", maxHeight: 220 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Session</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Steps</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Observed</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Counterfactual</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Avg reward</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Total reward</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(report.per_session ?? []).length > 0 ? (
                      report.per_session.map((row) => (
                        <tr key={row.session_id} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "6px 8px", fontFamily: "ui-monospace, monospace", fontSize: "0.72rem", color: "var(--text-secondary)" }}>{row.session_id.slice(0, 8)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.steps}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.observed_steps}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.counterfactual_steps}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: rewardColor(row.average_reward) }}>{signed(row.average_reward)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{signed(row.total_reward)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{pct(row.final_coverage)}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={7} style={{ padding: "12px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>No per-session data.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div>
              <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                Per-action comparison
              </div>
              <div style={{ overflow: "auto", maxHeight: 200 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      <th style={{ textAlign: "left", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Action</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>RL samples</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>RL avg reward</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>JEV avg reward</th>
                      <th style={{ textAlign: "right", padding: "6px 8px", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.per_action && report.per_action.length > 0 ? (
                      [...report.per_action].sort((a, b) => (b.reward_delta ?? 0) - (a.reward_delta ?? 0)).map((row) => (
                        <tr key={row.action} style={{ borderBottom: "1px solid var(--border)" }}>
                          <td style={{ padding: "6px 8px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em" }}>{row.action}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.sample_size}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: rewardColor(row.average_reward) }}>{signed(row.average_reward)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums", color: rewardColor(row.baseline_average_reward) }}>{signed(row.baseline_average_reward)}</td>
                          <td style={{ padding: "6px 8px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600, color: row.reward_delta != null ? (row.reward_delta > 0 ? "var(--ok)" : row.reward_delta < 0 ? "var(--danger)" : "var(--text-muted)") : "var(--text-muted)" }}>
                            {row.reward_delta != null ? (row.reward_delta > 0 ? "+" : "") + row.reward_delta.toFixed(2) : "—"}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} style={{ padding: "12px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.78rem" }}>No per-action data.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div style={{ display: "flex", gap: 12, fontSize: "0.78rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
              <span>Avg info gain (JEV): <strong style={{ color: "var(--text-primary)" }}>{pct(report.baseline_metrics?.average_information_gain ?? 0)}</strong></span>
              <span>Avg info gain (RL): <strong style={{ color: "var(--text-primary)" }}>{pct(report.metrics.average_information_gain)}</strong></span>
              <span>Stop rate (JEV): <strong style={{ color: "var(--text-primary)" }}>{pct(report.baseline_metrics?.stop_rate ?? 0)}</strong></span>
              <span>Stop rate (RL): <strong style={{ color: "var(--text-primary)" }}>{pct(report.metrics.stop_rate)}</strong></span>
              <span>Duplicate rate (JEV): <strong style={{ color: "var(--text-primary)" }}>{pct(report.baseline_metrics?.duplicate_search_rate ?? 0)}</strong></span>
              <span>Duplicate rate (RL): <strong style={{ color: "var(--text-primary)" }}>{pct(report.metrics.duplicate_search_rate)}</strong></span>
              <span>Research cost (JEV): <strong style={{ color: "var(--text-primary)" }}>{report.baseline_metrics?.research_cost_seconds.toFixed(0)}s</strong></span>
              <span>Research cost (RL): <strong style={{ color: "var(--text-primary)" }}>{report.metrics.research_cost_seconds.toFixed(0)}s</strong></span>
            </div>
          </div>
        </div>
      )}

      {reportError && !reportLoading && (
        <div style={{ padding: "10px 12px", background: "var(--danger-soft)", border: "1px solid var(--danger-border)", borderRadius: 8, marginTop: 6, fontSize: "0.8rem", color: "var(--danger)" }}>
          <AlertCircle size={13} style={{ marginRight: 6 }} aria-hidden="true" />
          {reportError}
        </div>
      )}
    </div>
  );
}
function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color?: string }) {
  return (
    <div className="card" style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8 }}>
      <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
      <div style={{ fontSize: "1.1rem", fontWeight: 700, color: color ?? "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: 2 }}>{sub}</div>
    </div>
  );
}
function ComparisonCard({ label, value, color }: { label: string; value: number | null; color?: string }) {
  return (
    <div style={{ padding: "10px 14px", background: "var(--bg-subtle)", borderRadius: 8, textAlign: "center" }}>
      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
      <div style={{ fontSize: "1.2rem", fontWeight: 700, color: color ?? "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>
        {value != null ? (value > 0 ? "+" : "") + value.toFixed(2) : "—"}
      </div>
    </div>
  );
}
