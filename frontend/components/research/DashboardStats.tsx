"use client";

import React, { useCallback, useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  FileText,
  Gauge,
  Link2,
  Network,
  Scissors,
  Square,
} from "lucide-react";
import { ProgressRing, LinearProgress } from "@/components/ui/Progress";
import { MetricCard, ExplainerPanel } from "@/components/ui/InfoCard";
import type { ResearchSession } from "@/lib/types";

export interface LiveStats {
  sources: number;
  claims: number;
  nodes: number;
  edges: number;
  coverage: number;
  iteration: number;
  lastAction?: string;
  lastReasoning?: string;
  stopReason?: string;
  /** Model calls this session has spent so far (per-session budget telemetry). */
  llmCalls?: number;
  /** Model calls the session is allowed; sent alongside llmCalls by the backend. */
  budgetCalls?: number;
  /** Prompt + completion characters charged to the session context budget. */
  contextChars?: number;
  /** Context character allowance for the session. */
  contextBudget?: number;
}

interface DashboardStatsProps {
  stats: LiveStats;
  maxIterations: number;
  status: ResearchSession["status"];
  isDone: boolean;
  /** False when no coverage signal exists yet, so we never show a false 0%. */
  coverageKnown: boolean;
}

type MetricKey = "sources" | "claims" | "nodes" | "edges" | "coverage";

const EXPLAINER_ID = "metric-definition";

/** Compact character count: 940 → "940", 12_500 → "12.5k", 610_000 → "610k". */
function formatChars(value: number): string {
  if (value < 1000) return String(value);
  const k = value / 1000;
  return `${k >= 100 ? Math.round(k) : k.toFixed(1)}k`;
}

/** Amber from 80% of a budget, red from 95%: the point is warning, not alarm. */
const BUDGET_WARN_RATIO = 0.8;
const BUDGET_CRITICAL_RATIO = 0.95;

function budgetRatio(used: number, limit?: number): number | null {
  if (!limit || limit <= 0) return null;
  return used / limit;
}

function budgetTone(ratio: number | null): string {
  if (ratio === null) return "var(--text-muted)";
  if (ratio >= BUDGET_CRITICAL_RATIO) return "var(--danger)";
  if (ratio >= BUDGET_WARN_RATIO) return "var(--warn)";
  return "var(--text-muted)";
}

const DEFINITIONS: Record<MetricKey, { title: string; body: string }> = {
  sources: {
    title: "Sources",
    body: "Web pages and documents the search layer retrieved and kept after credibility filtering. Every claim in the report traces back to one of them, and each source is scored 0-100% for credibility.",
  },
  claims: {
    title: "Claims",
    body: "Atomic factual statements extracted from the source text. Each claim carries a confidence score and stays linked to the source it came from, so the evidence table can always be traced back to a document.",
  },
  nodes: {
    title: "KG Nodes",
    body: "Entities fused from your claims into the knowledge graph — one node per distinct subject, concept, person, place, or event. Repeated mentions of the same entity across sources collapse into a single node.",
  },
  edges: {
    title: "KG Edges",
    body: "Typed relationships between those entities (for example works_at or causes), weighted by how strongly the evidence supports them. Denser edges mean the evidence is better connected rather than a pile of isolated facts.",
  },
  coverage: {
    title: "Coverage",
    body: "The decision engine's estimate of how much of your question has been answered, from 0% to 100%. Research continues while each new iteration still adds information and stops when coverage converges, the information gain dries up, or the iteration cap is reached.",
  },
};

export function DashboardStats({
  stats,
  maxIterations,
  status,
  isDone,
  coverageKnown,
}: DashboardStatsProps) {
  const [openMetric, setOpenMetric] = useState<MetricKey | null>(null);

  const toggle = useCallback((key: MetricKey) => {
    setOpenMetric((current) => (current === key ? null : key));
  }, []);

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      setOpenMetric(null);
    }
  }, []);

  const coverageText = coverageKnown
    ? `${Math.round(stats.coverage * 100)}%`
    : "—";

  const callsKnown = typeof stats.llmCalls === "number";
  const contextKnown = typeof stats.contextChars === "number";
  const callBudgetText = stats.budgetCalls ? ` / ${stats.budgetCalls}` : "";
  const contextBudgetText = stats.contextBudget
    ? ` / ${formatChars(stats.contextBudget)}`
    : "";

  // Session budget is finite, so the spend line has to say when it is running
  // out rather than quietly turning red at the very end.
  const callRatio = callsKnown
    ? budgetRatio(stats.llmCalls as number, stats.budgetCalls)
    : null;
  const contextRatio = contextKnown
    ? budgetRatio(stats.contextChars as number, stats.contextBudget)
    : null;
  const budgetNearlySpent = [callRatio, contextRatio].some(
    (ratio) => ratio !== null && ratio >= BUDGET_WARN_RATIO
  );

  const stopIcon =
    status === "completed" ? (
      <CircleCheck size={14} aria-hidden="true" />
    ) : status === "stopped" ? (
      <Square size={13} aria-hidden="true" />
    ) : (
      <CircleAlert size={14} aria-hidden="true" />
    );

  const stopLabel =
    status === "completed"
      ? "Completed"
      : status === "stopped"
      ? "Stopped"
      : "Ended";

  const metrics: {
    key: MetricKey;
    label: string;
    value: string | number;
    color: string;
    icon: React.ReactNode;
  }[] = [
    {
      key: "sources",
      label: "Sources",
      value: stats.sources,
      color: "var(--chart-2)",
      icon: <FileText size={18} />,
    },
    {
      key: "claims",
      label: "Claims",
      value: stats.claims,
      color: "var(--chart-1)",
      icon: <Scissors size={18} />,
    },
    {
      key: "nodes",
      label: "KG Nodes",
      value: stats.nodes,
      color: "var(--chart-3)",
      icon: <Network size={18} />,
    },
    {
      key: "edges",
      label: "KG Edges",
      value: stats.edges,
      color: "var(--chart-4)",
      icon: <Link2 size={18} />,
    },
  ];

  return (
    <>
      {/* Progress bar for iterations */}
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: 4,
            fontSize: "0.72rem",
            color: "var(--text-muted)",
          }}
        >
          <span>
            Iteration <span className="mono-num">{stats.iteration}</span> /{" "}
            <span className="mono-num">{maxIterations}</span>
          </span>
          <span className="mono-num">
            {coverageText}
            {coverageKnown ? " coverage" : " coverage (pending)"}
          </span>
        </div>
        <LinearProgress value={stats.iteration / maxIterations} />

        {/* Spend telemetry: how much of the session's model allowance is gone. */}
        {(callsKnown || contextKnown) && (
          <div
            style={{
              display: "flex",
              gap: 14,
              flexWrap: "wrap",
              marginTop: 6,
              fontSize: "0.7rem",
              color: "var(--text-muted)",
            }}
          >
            {callsKnown && (
              <span
                title="LLM calls used by this run against its per-session call budget."
                style={{ color: budgetTone(callRatio) }}
              >
                Model calls{" "}
                <span className="mono-num">
                  {stats.llmCalls}
                  {callBudgetText}
                </span>
              </span>
            )}
            {contextKnown && (
              <span
                title="Prompt and completion characters charged to this session's context budget."
                style={{ color: budgetTone(contextRatio) }}
              >
                Context <span className="mono-num">{formatChars(stats.contextChars as number)}{contextBudgetText}</span> chars
              </span>
            )}
            {budgetNearlySpent && (
              <span style={{ color: "var(--warn)", fontWeight: 600 }}>
                Budget nearly spent — the run stops when it hits this limit.
              </span>
            )}
          </div>
        )}
      </div>

      {isDone && stats.stopReason && (
        <div
          style={{
            fontSize: "0.78rem",
            color: "var(--text-secondary)",
            padding: "8px 12px",
            borderRadius: 8,
            background: "var(--bg-subtle)",
            border: "1px solid var(--border)",
            display: "flex",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              fontWeight: 600,
              flexShrink: 0,
              color:
                status === "completed"
                  ? "var(--ok)"
                  : status === "stopped"
                  ? "var(--warn)"
                  : "var(--danger)",
            }}
          >
            {stopIcon}
            {stopLabel}
          </span>
          <span>{stats.stopReason}</span>
        </div>
      )}

      {/* Live metrics: each card explains itself on click */}
      <div className="stats-grid" onKeyDown={onKeyDown}>
        {metrics.map((metric) => (
          <MetricCard
            key={metric.key}
            label={metric.label}
            value={metric.value}
            icon={metric.icon}
            color={metric.color}
            active={openMetric === metric.key}
            panelId={EXPLAINER_ID}
            onToggle={() => toggle(metric.key)}
          />
        ))}
      </div>

      {openMetric && (
        <ExplainerPanel
          id={EXPLAINER_ID}
          title={DEFINITIONS[openMetric].title}
          onClose={() => setOpenMetric(null)}
        >
          {DEFINITIONS[openMetric].body}
        </ExplainerPanel>
      )}

      {/* Coverage + last decision */}
      <div className="coverage-grid" onKeyDown={onKeyDown}>
        <MetricCard
          label="Coverage"
          value={coverageKnown ? coverageText : "—"}
          icon={<Gauge size={18} />}
          color="var(--chart-1)"
          active={openMetric === "coverage"}
          panelId={EXPLAINER_ID}
          onToggle={() => toggle("coverage")}
        >
          <span
            aria-hidden="true"
            style={{ display: "block", margin: "4px 0" }}
          >
            <ProgressRing
              value={coverageKnown ? stats.coverage : 0}
              size={72}
              strokeWidth={6}
            />
          </span>
        </MetricCard>

        {stats.lastAction && (
          <div className="card" style={{ padding: "16px 20px" }}>
            <p
              style={{
                fontSize: "0.72rem",
                color: "var(--text-muted)",
                fontWeight: 600,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                marginBottom: 6,
              }}
            >
              Last JEV Decision
            </p>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                marginBottom: 8,
              }}
            >
              <span className="badge badge-purple">{stats.lastAction}</span>
            </div>
            {stats.lastReasoning && (
              <p
                style={{
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                }}
              >
                {stats.lastReasoning}
              </p>
            )}
          </div>
        )}
      </div>
    </>
  );
}
