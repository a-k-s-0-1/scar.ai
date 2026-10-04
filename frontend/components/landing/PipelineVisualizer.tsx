"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Brain,
  CheckCircle,
  FileSearch,
  FileText,
  Network,
  Scissors,
} from "lucide-react";

interface Step {
  id: number;
  title: string;
  short: string;
  icon: React.ComponentType<{ size?: number; style?: React.CSSProperties }>;
  color: string;
  badge: string;
  description: string;
  formula?: string;
  inputs: string[];
  outputs: string[];
  modelTier: string;
}

const STEPS: Step[] = [
  {
    id: 1,
    title: "Discovery & Credibility Scoring",
    short: "Search",
    icon: FileSearch,
    color: "#38bdf8",
    badge: "Tavily + Academic Scoring",
    description:
      "Issues adaptive web search queries based on the evolving investigation state. Each retrieved document is parsed, stripped of boilerplate, deduplicated via SHA-256 hashes, and assigned a domain credibility score (0.3 for blogs up to 0.95 for peer-reviewed academic journals).",
    inputs: ["Research topic", "Gap exploration queries", "URL exclusion list"],
    outputs: ["Verified clean HTML sources", "Domain credibility weights (0.0 - 1.0)"],
    modelTier: "Tavily Web Search + Python heuristics",
  },
  {
    id: 2,
    title: "Atomic Proposition Extraction",
    short: "Extract",
    icon: Scissors,
    color: "#8b5cf6",
    badge: "Structured Claim Triples",
    description:
      "Reads source documents sentence by sentence, decomposing unstructured narrative into atomic factual triples: (Subject, Predicate, Object). Each claim is assigned an extraction confidence rating (High / Medium / Low) and permanently bound to its source document.",
    inputs: ["Raw source text", "Source document ID"],
    outputs: ["Atomic (S, P, O) claims", "Claim-to-source provenance records"],
    modelTier: "Tier 2: Google Gemini 3.8 Flash (Structured JSON mode)",
  },
  {
    id: 3,
    title: "Iterative Knowledge Fusion (IKF)",
    short: "Fuse",
    icon: Network,
    color: "#a855f7",
    badge: "Dynamic Knowledge Graph",
    description:
      "The IKF engine resolves mentions into canonical entities, forming a rich knowledge graph. Entities become nodes with types (concept, entity, mechanism, organization), while assertions become directional edges with cumulative weight. Multiple sources affirming the same relationship increase edge conviction.",
    inputs: ["Extracted claims", "Existing knowledge graph snapshot"],
    outputs: ["Canonical KnowledgeNodes", "Weighted KnowledgeEdges", "Adjacency matrix"],
    modelTier: "IKF Graph Engine (SQLAlchemy + Graph Memory)",
  },
  {
    id: 4,
    title: "Contradiction & Gap Detection",
    short: "Detect",
    icon: AlertTriangle,
    color: "#f59e0b",
    badge: "Empirical Conflict Isolation",
    description:
      "Pairs claims regarding the same entity and subjects them to rigorous cross-examination. Identifies empirical conflicts (e.g. Source A says 92% efficiency; Source B claims max 74%), classifies severity, and generates an explanatory note so discrepancies are never swept under the rug.",
    inputs: ["Overlapping claim pairs", "Graph entity clusters"],
    outputs: ["Contradiction records with severity ratings", "Identified knowledge gaps"],
    modelTier: "Tier 3: Groq Cloud (GPT-OSS 120B High-Reasoning)",
  },
  {
    id: 5,
    title: "Judgment Evaluation Vector (JEV)",
    short: "Decide",
    icon: Brain,
    color: "#ec4899",
    badge: "Autonomous Convergence Policy",
    description:
      "Rather than stopping after an arbitrary prompt, the JEV engine calculates asymptotic knowledge coverage: 1 - exp(-1.6 * ratio). It tracks novelty across consecutive iterations. If novelty plateaus with high coverage, it triggers STOP; otherwise, it directs targeted queries to fill unexplored facets.",
    formula: "Coverage = 1 - exp(-1.6 × (0.45·Claims + 0.25·Sources + 0.30·Entities))",
    inputs: ["Novelty delta", "Coverage ratio", "Unresolved contradictions"],
    outputs: ["Action: SEARCH | EXTRACT | VERIFY | EXPAND | STOP", "Reward signal logged for RL"],
    modelTier: "JEV Heuristic Policy Engine (RL State Tracker)",
  },
  {
    id: 6,
    title: "Evidence-Grounded Synthesis",
    short: "Synthesize",
    icon: FileText,
    color: "#10b981",
    badge: "Audited Report Generation",
    description:
      "Synthesizes an executive brief, core thematic findings, an interactive evidence table, and remaining unknowns. Every assertion is explicitly cited with bracketed references [1], [2] linked to origin URLs. Fallback provenance tags ensure total transparency regarding generation models.",
    inputs: ["Full knowledge graph", "Contradiction log", "All vetted citations"],
    outputs: ["Executive summary", "Evidence table", "Cited research report", "Exportable PDF/JSON"],
    modelTier: "Tier 3: Groq Cloud (GPT-OSS 120B) with Gemini Fallback",
  },
];

export function PipelineVisualizer() {
  const [activeStepId, setActiveStepId] = useState(1);
  const activeStep = STEPS.find((s) => s.id === activeStepId) || STEPS[0];

  return (
    <section id="pipeline" style={{ padding: "80px 0", borderTop: "1px solid var(--border)" }}>
      <div className="landing-container">
        {/* Section Header */}
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="landing-badge" style={{ marginBottom: 12 }}>
            The Autonomous Engine
          </span>
          <h2
            style={{
              fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: 16,
            }}
          >
            The 6-Step Closed Loop
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", lineHeight: 1.6 }}>
            Traditional search models stop at single-shot retrieval. SCAR operates in an
            autonomous feedback loop that checks its own work, detects knowledge gaps, and
            proves its claims.
          </p>
        </div>

        {/* Step Selector Pills */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 10,
            marginBottom: 32,
          }}
        >
          {STEPS.map((step) => {
            const isSelected = step.id === activeStepId;
            const Icon = step.icon;
            return (
              <button
                key={step.id}
                type="button"
                onClick={() => setActiveStepId(step.id)}
                style={{
                  padding: "14px 12px",
                  borderRadius: 12,
                  border: isSelected
                    ? `1px solid ${step.color}`
                    : "1px solid var(--border)",
                  background: isSelected
                    ? "rgba(255, 255, 255, 0.05)"
                    : "rgba(255, 255, 255, 0.02)",
                  boxShadow: isSelected ? `0 0 20px ${step.color}25` : "none",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 8,
                  transition: "all 0.15s ease",
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 8,
                    background: `${step.color}18`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: step.color,
                  }}
                >
                  <Icon size={18} />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: "0.7rem",
                      fontWeight: 700,
                      color: isSelected ? step.color : "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    Phase 0{step.id}
                  </div>
                  <div
                    style={{
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                    }}
                  >
                    {step.short}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* Active Step Detailed Card */}
        <div
          className="landing-card"
          style={{
            padding: "32px 36px",
            border: `1px solid ${activeStep.color}40`,
            background: "rgba(18, 18, 25, 0.9)",
            boxShadow: `0 16px 40px rgba(0,0,0,0.5), 0 0 30px ${activeStep.color}15`,
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              flexWrap: "wrap",
              gap: 16,
              marginBottom: 20,
            }}
          >
            <div>
              <span
                style={{
                  display: "inline-block",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  color: activeStep.color,
                  letterSpacing: "0.06em",
                  marginBottom: 6,
                }}
              >
                Phase 0{activeStep.id} • {activeStep.badge}
              </span>
              <h3 style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--text-primary)" }}>
                {activeStep.title}
              </h3>
            </div>
            <span
              style={{
                fontSize: "0.78rem",
                padding: "6px 12px",
                borderRadius: 8,
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--border)",
                color: "var(--text-secondary)",
              }}
            >
              Engine: <strong style={{ color: "#e2e8f0" }}>{activeStep.modelTier}</strong>
            </span>
          </div>

          <p
            style={{
              fontSize: "1rem",
              color: "var(--text-secondary)",
              lineHeight: 1.7,
              marginBottom: 24,
            }}
          >
            {activeStep.description}
          </p>

          {activeStep.formula && (
            <div
              style={{
                padding: "12px 18px",
                borderRadius: 10,
                background: "rgba(0, 0, 0, 0.4)",
                border: "1px solid rgba(236, 72, 153, 0.3)",
                marginBottom: 24,
                fontFamily: "var(--font-mono)",
                fontSize: "0.85rem",
                color: "#f472b6",
              }}
            >
              {activeStep.formula}
            </div>
          )}

          {/* Inputs & Outputs Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
              gap: 20,
              paddingTop: 20,
              borderTop: "1px solid var(--border)",
            }}
          >
            <div>
              <div
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                  marginBottom: 10,
                  letterSpacing: "0.04em",
                }}
              >
                Input Vectors
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                {activeStep.inputs.map((inp) => (
                  <li
                    key={inp}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: "0.85rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <CheckCircle size={14} style={{ color: activeStep.color, flexShrink: 0 }} />
                    <span>{inp}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <div
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                  marginBottom: 10,
                  letterSpacing: "0.04em",
                }}
              >
                Generated Artifacts
              </div>
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
                {activeStep.outputs.map((out) => (
                  <li
                    key={out}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: "0.85rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    <ArrowRight size={14} style={{ color: activeStep.color, flexShrink: 0 }} />
                    <span>{out}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
