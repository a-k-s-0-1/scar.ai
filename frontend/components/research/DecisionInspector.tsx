"use client";

import React, { useEffect, useState } from "react";
import { Brain, AlertTriangle, GitBranch } from "lucide-react";
import { getDecisionInspector } from "@/lib/api";
import { StateInspector } from "@/lib/state-inspector";
import type { DecisionInspectorEntry, ShadowPrediction } from "@/lib/types";

interface DecisionInspectorProps {
  sessionId: string;
  className?: string;
}

type ViewMode = "list" | "detail";

function decisionColor(agrees: boolean) {
  return agrees ? "var(--ok)" : "var(--warn)";
}

export function DecisionInspector({ sessionId, className = "" }: DecisionInspectorProps) {
  const [entries, setEntries] = useState<DecisionInspectorEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>("list");
  const [activeIdx, setActiveIdx] = useState<number | null>(null);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const res = await getDecisionInspector(sessionId);
        if (!ignore) setEntries(res.entries);
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : "Could not load decision inspector.");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  if (loading) {
    return (
      <div className={`card ${className}`} style={{ padding: "18px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
          <Brain size={15} style={{ color: "var(--accent)" }} aria-hidden="true" />
          <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)", letterSpacing: "0.02em" }}>
            Decision inspector
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8 }}>
              <div style={{ height: 14, width: "60%", background: "var(--border)", borderRadius: 4, marginBottom: 8 }} />
              <div style={{ display: "flex", gap: 8 }}>
                <div style={{ height: 10, width: 60, background: "var(--border)", borderRadius: 4 }} />
                <div style={{ height: 10, width: 80, background: "var(--border)", borderRadius: 4 }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`card ${className}`} style={{ padding: "18px 20px", color: "var(--danger)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <Brain size={15} aria-hidden="true" />
          <span style={{ fontWeight: 700, fontSize: "0.85rem", letterSpacing: "0.02em" }}>Decision inspector</span>
        </div>
        <p style={{ fontSize: "0.85rem", margin: 0 }}>{error}</p>
      </div>
    );
  }

  if (entries.length === 0) {
    return (
      <div className={`card ${className}`} style={{ padding: "18px 20px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <Brain size={15} style={{ color: "var(--accent)" }} aria-hidden="true" />
          <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)", letterSpacing: "0.02em" }}>
            Decision inspector
          </span>
        </div>
        No recorded decisions exist for this session yet.
      </div>
    );
  }

  return (
    <div className={`card ${className}`} style={{ padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <Brain size={15} style={{ color: "var(--accent)" }} aria-hidden="true" />
        <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)", letterSpacing: "0.02em" }}>
          Decision inspector
        </span>
        <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "var(--text-muted)" }}>
          {entries.length} decision{entries.length === 1 ? "" : "s"} · {entries.filter((e) => e.disagreement).length} disagreement{entries.filter((e) => e.disagreement).length === 1 ? "" : "s"}
        </span>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button
          type="button"
          className={`btn-secondary${mode === "list" ? " btn-active" : ""}`}
          onClick={() => { setMode("list"); setActiveIdx(null); }}
          style={{ padding: "5px 10px", fontSize: "0.78rem" }}
        >
          List
        </button>
        <button
          type="button"
          className={`btn-secondary${mode === "detail" ? " btn-active" : ""}`}
          onClick={() => { setMode("detail"); setActiveIdx(activeIdx ?? 0); }}
          style={{ padding: "5px 10px", fontSize: "0.78rem" }}
        >
          Detail
        </button>
      </div>

      {mode === "list" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {entries.map((entry) => (
            <div
              key={entry.iteration}
              style={{
                padding: "10px 12px",
                background: "var(--bg-subtle)",
                borderRadius: 8,
                borderLeft: `2px solid ${entry.disagreement ? "var(--warn)" : "var(--bg-subtle)"}`,
                cursor: "pointer",
                transition: "background var(--duration-fast) var(--ease-standard)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "var(--bg-subtle)")}
              onClick={() => { setMode("detail"); setActiveIdx(entry.iteration); }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: "var(--text-muted)", fontSize: "0.78rem", fontFamily: "ui-monospace, monospace" }}>
                  iter {entry.iteration}
                </span>
                <span style={{ fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--accent-ink)" }}>
                  {entry.actual_action ?? entry.jev_action ?? "?"}
                </span>
                {entry.disagreement && (
                  <span style={{ display: "flex", alignItems: "center", gap: 4, color: decisionColor(true), fontSize: "0.75rem" }}>
                    <AlertTriangle size={12} aria-hidden="true" />
                    <span style={{ color: "var(--text-muted)" }}>RL wanted {entry.rl_action}</span>
                  </span>
                )}
                {!entry.disagreement && entry.rl_action && entry.rl_action !== entry.jev_action && (
                  <span style={{ display: "flex", alignItems: "center", gap: 4, color: decisionColor(true), fontSize: "0.75rem" }}>
                    <GitBranch size={12} aria-hidden="true" />
                    <span style={{ color: "var(--text-muted)" }}>shadow differs</span>
                  </span>
                )}
                {entry.reward != null && (
                  <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", fontSize: "0.82rem", fontWeight: 700, color: entry.reward >= 0 ? "var(--ok)" : "var(--danger)" }}>
                    {entry.reward >= 0 ? "+" : ""}{entry.reward.toFixed(2)}
                  </span>
                )}
              </div>
              {entry.jev_reasoning && (
                <div style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginTop: 4, maxWidth: 600 }}>
                  {entry.jev_reasoning}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {mode === "detail" && activeIdx != null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {entries
            .filter((e) => e.iteration === activeIdx)
            .map((entry) => (
              <div key={entry.iteration}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                    Iteration {entry.iteration}
                  </span>
                  {entry.disagreement && (
                    <span style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--warn)", fontSize: "0.75rem" }}>
                      <AlertTriangle size={13} aria-hidden="true" />
                      JEV and RL disagreed
                    </span>
                  )}
                  {entry.reward != null && (
                    <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", fontSize: "0.85rem", fontWeight: 700, color: entry.reward >= 0 ? "var(--ok)" : "var(--danger)" }}>
                      {entry.reward >= 0 ? "+" : ""}{entry.reward.toFixed(2)}
                    </span>
                  )}
                </div>

                <StateInspector
                  state={entry.state as Parameters<typeof StateInspector>[0]["state"]}
                  stateHash={entry.state_key}
                  totalReward={entry.reward}
                  rewardComponents={entry.reward_components}
                  rewardExplanation={entry.reward_explanation}
                  latestPrediction={
                    (entry.rl_action || entry.jev_action)
                      ? {
                          id: `shadow-${entry.iteration}`,
                          iteration: entry.iteration,
                          state_key: entry.state_key ?? "",
                          jev_action: entry.jev_action ?? "",
                          jev_reasoning: entry.jev_reasoning ?? "",
                          jev_expected_value: entry.jev_expected_value,
                          rl_action: entry.rl_action ?? "",
                          rl_expected_value: entry.rl_expected_value,
                          rl_scores: entry.rl_scores,
                          rl_support: entry.rl_support,
                          fallback: entry.rl_action == null,
                          disagreement: entry.disagreement,
                        } as ShadowPrediction
                      : undefined
                  }
                  className=""
                />

                <div style={{ marginTop: 12, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                    Decision
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px" }}>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>Action chosen</div>
                      <div style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                        {entry.actual_action ?? entry.jev_action ?? "?"}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>Available actions</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {(entry.available_actions ?? []).length > 0 ? (
                          entry.available_actions.map((a) => (
                            <span
                              key={a}
                              className={`tag ${a === (entry.actual_action ?? entry.jev_action) ? "tag-green" : "tag-gray"}`}
                              style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.04em" }}
                            >
                              {a}
                            </span>
                          ))
                        ) : (
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>not recorded</span>
                        )}
                      </div>
                    </div>
                    {entry.rl_action && entry.rl_action !== entry.jev_action && (
                      <div>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>RL would pick</div>
                        <div style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--chart-2)" }}>
                          {entry.rl_action}
                        </div>
                      </div>
                    )}
                    <div>
                      <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>Reasoning</div>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", maxWidth: 420 }}>
                        {entry.jev_reasoning ?? "—"}
                      </div>
                    </div>
                  </div>
                </div>

                {entry.information_gain != null && (
                  <div style={{ marginTop: 10, fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Information gain: {(entry.information_gain * 100).toFixed(1)}% · coverage after: {(entry.coverage_after != null ? entry.coverage_after * 100 : 0).toFixed(1)}%
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
