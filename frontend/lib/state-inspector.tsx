"use client";

import React from "react";
import { FileJson, Hash } from "lucide-react";
import type { ResearchStateSnapshot, RewardExplanationRow, ShadowPrediction } from "@/lib/types";

export interface StateInspectorProps {
  state: ResearchStateSnapshot | null;
  stateHash?: string | null;
  stateBytes?: number;
  rewardComponents?: Record<string, number>;
  rewardExplanation?: RewardExplanationRow[];
  totalReward?: number | null;
  latestPrediction?: ShadowPrediction | null;
  className?: string;
}

type ScoreClassKey = 1 | -1 | 0;
type ScoreClassValue = "dot-dot dot-ok" | "dot-dot dot-warn" | "dot-dot dot-gray";

function scoreClassKey(value: number): ScoreClassKey {
  if (value > 0) return 1;
  if (value < 0) return -1;
  return 0;
}

const SCORE_CLASS_MAP: Readonly<Record<ScoreClassKey, ScoreClassValue>> = {
  1: "dot-dot dot-ok",
  "-1": "dot-dot dot-warn",
  0: "dot-dot dot-gray",
} as const;

function scoreClass(value: number): ScoreClassValue {
  return SCORE_CLASS_MAP[scoreClassKey(value)];
}

function bold(value: number): string {
  return value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2);
}

export function StateInspector({
  state,
  stateHash,
  stateBytes,
  rewardExplanation,
  totalReward,
  latestPrediction,
  className = "",
}: StateInspectorProps) {
  if (!state) {
    return (
      <div className={`card ${className}`} style={{ padding: "18px 20px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
        No formal research state is available yet for this session.
      </div>
    );
  }

  return (
    <div className={`card ${className}`} style={{ padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <FileJson size={15} style={{ color: "var(--accent)" }} aria-hidden="true" />
        <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)", letterSpacing: "0.02em" }}>
          Research state
        </span>
        {stateHash && (
          <span style={{ marginLeft: "auto", fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" }}>
            hash {stateHash} · {stateBytes}B
          </span>
        )}
      </div>

      {/* iteration / budget */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 18px", marginBottom: 16 }}>
        <StateField label="Iteration" value={String(state.iteration)} />
        <StateField label="Depth" value={state.depth} />
        <StateField label="Max iterations" value={String(state.max_iterations)} />
        <StateField label="Time elapsed" value={state.time_elapsed.toFixed(1) + "s"} />
        <StateField label="Remaining time" value={state.remaining_time.toFixed(1) + "s"} />
        <StateField label="Search budget left" value={String(state.remaining_search_budget)} />
        <StateField label="LLM budget left" value={String(state.remaining_llm_budget)} />
      </div>

      {/* counts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 18px", marginBottom: 16 }}>
        <StateField label="Sources" value={String(state.total_sources)} />
        <StateField label="Claims" value={String(state.total_claims)} />
        <StateField label="Nodes" value={String(state.total_nodes)} />
        <StateField label="Edges" value={String(state.total_edges)} />
        <StateField label="Coverage" value={(state.coverage * 100).toFixed(1) + "%"} />
        <StateField label="Facet coverage" value={(state.facet_coverage * 100).toFixed(1) + "%"} />
        <StateField label="Info gain" value={(state.information_gain * 100).toFixed(1) + "%"} />
        <StateField label="Source quality" value={(state.source_quality * 100).toFixed(0) + ""} />
        <StateField label="Source diversity" value={String(state.source_diversity)} />
        <StateField label="Open contradictions" value={String(state.unresolved_contradictions)} />
        <StateField label="Resolved contradictions" value={String(state.resolved_contradictions)} />
        <StateField label="Duplicate claims" value={String(state.duplicate_count)} />
        <StateField label="Plateau iterations" value={String(state.plateau_iterations)} />
        <StateField label="LLM calls" value={String(state.llm_calls)} />
        <StateField label="Previous action" value={state.previous_action ?? "—"} mono />
        <StateField label="Previous reward" value={state.previous_reward != null ? bold(state.previous_reward) : "—"} />
      </div>

      {/* unresolved gaps */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4 }}>Unresolved gaps</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          {state.unresolved_gaps.length > 0 ? (
            state.unresolved_gaps.slice(0, 8).map((g) => (
              <span
                key={g}
                className="tag tag-gray"
                style={{ fontSize: "0.72rem", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {g}
              </span>
            ))
          ) : (
            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>none</span>
          )}
          {state.unresolved_gaps.length > 8 && (
            <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>+{state.unresolved_gaps.length - 8} more</span>
          )}
        </div>
      </div>

      {/* confidence distribution */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4 }}>Confidence distribution</div>
        <div style={{ display: "flex", gap: 12 }}>
          {(["high", "medium", "low"] as const).map((band) => {
            const count = state.confidence_distribution[band] ?? 0;
            return (
              <div key={band} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>{band}:</span>
                <span style={{ fontVariantNumeric: "tabular-nums", fontSize: "0.82rem" }}>{count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* current query */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginBottom: 4 }}>Current query</div>
        <div style={{ fontSize: "0.82rem", color: "var(--text-primary)", wordBreak: "break-word" }}>
          {state.current_query ?? "—"}
        </div>
      </div>

      {/* reward breakdown */}
      {rewardExplanation && rewardExplanation.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginTop: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--text-secondary)", letterSpacing: "0.03em" }}>
              Reward breakdown
            </span>
            {totalReward != null && (
              <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", fontSize: "0.85rem", fontWeight: 700, color: totalReward >= 0 ? "var(--ok)" : "var(--danger)" }}>
                {bold(totalReward)}
              </span>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {rewardExplanation.map((row) => (
              <div
                key={row.component}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "4px 8px",
                  borderRadius: 6,
                  background: "var(--bg-subtle)",
                  fontSize: "0.78rem",
                }}
              >
                <span style={{ flex: 1, color: "var(--text-secondary)" }}>{row.reason}</span>
                <span className={scoreClass(row.value)} style={{ flex: 1, height: "100%" }} />
                <span style={{ fontVariantNumeric: "tabular-nums", fontWeight: 600, color: row.direction === "credit" ? "var(--ok)" : "var(--warn)" }}>
                  {bold(row.value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* shadow prediction */}
      {latestPrediction && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 14, marginTop: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <Hash size={14} style={{ color: "var(--chart-2)" }} aria-hidden="true" />
            <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "var(--text-secondary)", letterSpacing: "0.03em" }}>
              Shadow prediction
            </span>
            {latestPrediction.fallback && (
              <span className="badge badge-gray" style={{ fontSize: "0.65rem" }}>JEV reference</span>
            )}
            {!latestPrediction.fallback && latestPrediction.disagreement && (
              <span className="badge badge-warn" style={{ fontSize: "0.65rem" }}>disagreement</span>
            )}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px 16px" }}>
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>JEV chose</div>
              <div style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {latestPrediction.jev_action}
              </div>
              {latestPrediction.jev_reasoning && (
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: 2, maxWidth: 340 }}>
                  {latestPrediction.jev_reasoning}
                </div>
              )}
              {latestPrediction.jev_expected_value != null && (
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
                  expected value {latestPrediction.jev_expected_value.toFixed(2)}
                </div>
              )}
            </div>
            <div>
              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 2 }}>RL would recommend</div>
              <div style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.04em", color: latestPrediction.disagreement ? "var(--chart-2)" : "var(--text-primary)" }}>
                {latestPrediction.rl_action}
              </div>
              {latestPrediction.rl_expected_value != null && (
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
                  estimated value {latestPrediction.rl_expected_value.toFixed(2)}
                </div>
              )}
              {!latestPrediction.fallback && (
                <div style={{ marginTop: 6, padding: "4px 8px", background: "var(--bg-subtle)", borderRadius: 6, fontSize: "0.7rem", color: "var(--text-secondary)" }}>
                  support {latestPrediction.rl_support} · {Object.keys(latestPrediction.rl_scores).length} action scores
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StateField({ label, value, mono }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: 8, alignItems: "center" }}>
      <span style={{ color: "var(--text-secondary)", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.03em" }}>
        {label}
      </span>
      <span style={{ fontSize: "0.82rem", color: "var(--text-primary)", fontVariantNumeric: mono ? "ui-monospace, monospace" : "normal" }}>
        {value}
      </span>
    </div>
  );
}
