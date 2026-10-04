"use client";

import React from "react";
import {
  AlertTriangle,
  Brain,
  FileSearch,
  Layers,
  Network,
  Scissors,
  Target,
  Zap,
  RotateCcw,
  BarChart3,
  GitBranch,
  Loader2,
  Clock,
} from "lucide-react";

const PIPELINE = [
  {
    Icon: FileSearch,
    title: "Search the web",
    body: "Every iteration issues fresh web queries through the Tavily search API and keeps the most credible, non-duplicate sources.",
  },
  {
    Icon: Scissors,
    title: "Extract claims",
    body: "Sources are read clause by clause and turned into atomic claims, each with a confidence score and a link back to its document.",
  },
  {
    Icon: Network,
    title: "Fuse knowledge",
    body: "Claims are fused into a knowledge graph: entities become nodes, relationships become weighted edges, and duplicate mentions collapse together.",
  },
  {
    Icon: AlertTriangle,
    title: "Detect contradictions",
    body: "Conflicting claim pairs are flagged with a severity and an explanation, so the report shows where sources genuinely disagree.",
  },
  {
    Icon: Brain,
    title: "Decide and report",
    body: "The decision engine weighs information gain against coverage, then either runs another iteration or stops and writes the final report.",
  },
];

const DEPTHS = [
  {
    name: "Quick",
    iterations: "3",
    sources: "10",
    claims: "30",
    entities: "40",
    time: "about 3 min",
  },
  {
    name: "Standard",
    iterations: "5",
    sources: "15",
    claims: "60",
    entities: "80",
    time: "about 5 min",
  },
  {
    name: "Deep",
    iterations: "8",
    sources: "25",
    claims: "120",
    entities: "160",
    time: "about 8 min",
  },
];

const STACK = [
  { name: "Tavily Search", role: "web retrieval for every iteration" },
  { name: "Gemini 3.8 Flash", role: "claim extraction and report synthesis" },
  { name: "Groq 120B", role: "fast reasoning for decision steps" },
  { name: "IKF Knowledge Fusion", role: "entity and relationship fusion" },
  { name: "JEV Decision Engine", role: "continue / stop decisions and coverage" },
  { name: "Adaptive Research Planner", role: "facet-aware query planning and coverage tracking" },
  { name: "Search Memory", role: "negative-result cache to skip dead-end queries" },
  { name: "FastAPI + SQLAlchemy", role: "API, orchestration and persistence" },
  { name: "Next.js + React", role: "this interface, including the live stream" },
  { name: "vis-network", role: "interactive knowledge-graph rendering" },
];

const CAPABILITIES = [
  {
    Icon: Target,
    title: "Adaptive research planning",
    body: "Breaks each question into the dimensions worth researching and tracks coverage per dimension, so the next search targets the largest useful gap instead of just the next generated query.",
  },
  {
    Icon: Loader2,
    title: "Negative-result caching",
    body: "Remembers search queries that returned no useful evidence and skips near-duplicates, so a dead-end is not paid for twice in the same run.",
  },
  {
    Icon: RotateCcw,
    title: "One-click synthesis retry",
    body: "If the report summary fell back to rule-based text, a single button re-runs only the summarization step — cheap, fast, and it reuses everything the run already found.",
  },
  {
    Icon: BarChart3,
    title: "Coverage by dimension",
    body: "Shows how much evidence exists per research dimension and highlights which angles are still missing, both during a live run and in a finished report.",
  },
  {
    Icon: Zap,
    title: "Per-session budgets",
    body: "Each session has its own LLM call and context budgets, so one run cannot burn through the limits by accident.",
  },
  {
    Icon: GitBranch,
    title: "Versioned knowledge",
    body: "Claims from different sources are tracked separately, so the report can show how the evidence evolved rather than pretending every source said the same thing.",
  },
  {
    Icon: Clock,
    title: "Durable session events",
    body: "Every run records a replayable event log, so a finished investigation can be reopened with its execution history instead of an empty activity tab.",
  },
];

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ padding: "20px 22px" }}>
      <h3
        style={{
          fontSize: "0.95rem",
          fontWeight: 700,
          color: "var(--text-primary)",
          marginBottom: 12,
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

export function AboutPanel() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Card title="What this is">
        <p
          style={{
            fontSize: "0.88rem",
            color: "var(--text-secondary)",
            lineHeight: 1.65,
          }}
        >
          SCAR (Self-Correcting Agent for Research). You ask a question, and it searches
          the web repeatedly, extracts the factual claims from what it finds,
          fuses them into a knowledge graph, looks for contradictions, and
          decides for itself whether another iteration is worth running. When it
          stops you get an evidence-grounded report: summary, key findings,
          claims with citations, disagreements, and the gaps it could not close.
        </p>
      </Card>

      <Card title="Current capabilities">
        <ul
          style={{
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 0,
          }}
        >
          {CAPABILITIES.map(({ Icon, title, body }) => (
            <li key={title} style={{ display: "flex", gap: 12 }}>
              <span
                aria-hidden="true"
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 9,
                  background: "var(--accent-soft)",
                  border: "1px solid var(--accent-border)",
                  color: "var(--accent-ink)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Icon size={15} />
              </span>
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "0.84rem",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    marginBottom: 2,
                  }}
                >
                  {title}
                </div>
                <p
                  style={{
                    fontSize: "0.82rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.55,
                  }}
                >
                  {body}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="How a run works">
        <ol
          style={{
            listStyle: "none",
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 0,
          }}
        >
          {PIPELINE.map(({ Icon, title, body }, index) => (
            <li key={title} style={{ display: "flex", gap: 12 }}>
              <span
                aria-hidden="true"
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 9,
                  background: "var(--accent-soft)",
                  border: "1px solid var(--accent-border)",
                  color: "var(--accent-ink)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                <Icon size={15} />
              </span>
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: "0.84rem",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    marginBottom: 2,
                  }}
                >
                  <span
                    className="mono-num"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {index + 1}.
                  </span>{" "}
                  {title}
                </div>
                <p
                  style={{
                    fontSize: "0.82rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.55,
                  }}
                >
                  {body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <Card title="Research depth profiles">
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "0.8rem",
            }}
          >
            <thead>
              <tr
                style={{ color: "var(--text-muted)", textAlign: "left" }}
              >
                <th
                  style={{ padding: "6px 10px 6px 0", fontWeight: 600 }}
                >
                  Depth
                </th>
                <th
                  style={{ padding: "6px 10px", fontWeight: 600 }}
                >
                  Iterations
                </th>
                <th
                  style={{ padding: "6px 10px", fontWeight: 600 }}
                >
                  Source target
                </th>
                <th
                  style={{ padding: "6px 10px", fontWeight: 600 }}
                >
                  Claim target
                </th>
                <th
                  style={{ padding: "6px 10px", fontWeight: 600 }}
                >
                  Entity target
                </th>
                <th
                  style={{ padding: "6px 0 6px 10px", fontWeight: 600 }}
                >
                  Typical time
                </th>
              </tr>
            </thead>
            <tbody>
              {DEPTHS.map((row) => (
                <tr
                  key={row.name}
                  style={{
                    borderTop: "1px solid var(--border)",
                    color: "var(--text-secondary)",
                  }}
                >
                  <td
                    style={{
                      padding: "8px 10px 8px 0",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                    }}
                  >
                    {row.name}
                  </td>
                  <td className="mono-num" style={{ padding: "8px 10px" }}>
                    {row.iterations}
                  </td>
                  <td className="mono-num" style={{ padding: "8px 10px" }}>
                    {row.sources}
                  </td>
                  <td className="mono-num" style={{ padding: "8px 10px" }}>
                    {row.claims}
                  </td>
                  <td className="mono-num" style={{ padding: "8px 10px" }}>
                    {row.entities}
                  </td>
                  <td style={{ padding: "8px 0 8px 10px" }}>
                    {row.time}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Technology stack">
        <ul
          style={{
            listStyle: "none",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 10,
            padding: 0,
          }}
        >
          {STACK.map((item) => (
            <li
              key={item.name}
              style={{
                padding: "10px 12px",
                borderRadius: 10,
                background: "var(--bg-subtle)",
                border: "1px solid var(--border)",
                display: "flex",
                gap: 10,
                alignItems: "flex-start",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  color: "var(--accent-ink)",
                  marginTop: 2,
                  display: "flex",
                }}
              >
                <Layers size={14} />
              </span>
              <span>
                <span
                  style={{
                    display: "block",
                    fontSize: "0.82rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {item.name}
                </span>
                <span
                  style={{
                    display: "block",
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                  }}
                >
                  {item.role}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Where the numbers come from">
        <p
          style={{
            fontSize: "0.82rem",
            color: "var(--text-secondary)",
            lineHeight: 1.6,
          }}
        >
          Source, claim, node and edge counts are the real totals persisted for
          the run. Coverage and the stop reason are reported by the decision
          engine, so a session reopened from history shows the values stored with
          its report rather than inventing live ones. If a number was never
          recorded it is shown as a dash, never as a zero.
        </p>
      </Card>
    </div>
  );
}
