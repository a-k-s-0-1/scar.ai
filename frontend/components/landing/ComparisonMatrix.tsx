"use client";

import React from "react";
import { Check, X } from "lucide-react";

const COMPARISON_ROWS = [
  {
    feature: "Retrieval Architecture",
    rag: "Single-shot keyword/vector query; cannot adapt after initial search",
    ragStatus: false,
    scar: "Autonomous multi-iteration loop with dynamic query expansion to fill knowledge gaps",
    scarStatus: true,
  },
  {
    feature: "Knowledge Representation",
    rag: "Flat text chunks stored in vector embeddings (loses relational structure)",
    ragStatus: false,
    scar: "Dynamic Knowledge Graph (IKF) with entity canonicalization and weighted relationship edges",
    scarStatus: true,
  },
  {
    feature: "Handling Conflicting Sources",
    rag: "Blends contradictory text into an arbitrary average, causing silent hallucinations",
    ragStatus: false,
    scar: "Dedicated LLM contradiction detector isolates disagreements and assigns severity ratings",
    scarStatus: true,
  },
  {
    feature: "Convergence & Stopping Logic",
    rag: "Stops blindly after a fixed token count or single prompt response",
    ragStatus: false,
    scar: "Judgment Evaluation Vector (JEV) evaluates asymptotic coverage and consecutive novelty plateaus",
    scarStatus: true,
  },
  {
    feature: "Evidence Grounding & Provenance",
    rag: "Fuzzy chunk context with high probability of hallucinated citations",
    ragStatus: false,
    scar: "Strict atomic triples linked to verified source IDs with SHA-256 deduplication and numbered citations",
    scarStatus: true,
  },
  {
    feature: "Source Credibility Weighting",
    rag: "Treats random forum posts and peer-reviewed journals with equal semantic weight",
    ragStatus: false,
    scar: "Academic heuristics assign credibility scores (0.3 for blogs up to 0.95 for .edu/.gov/peer-reviewed)",
    scarStatus: true,
  },
];

export function ComparisonMatrix() {
  return (
    <section id="comparison" style={{ padding: "80px 0", borderTop: "1px solid var(--border)" }}>
      <div className="landing-container">
        {/* Header */}
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="landing-badge" style={{ marginBottom: 12 }}>
            Architectural Differentiation
          </span>
          <h2
            style={{
              fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: 16,
            }}
          >
            Why Single-Shot RAG Fails Deep Research
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", lineHeight: 1.6 }}>
            Most AI search engines are simply retrieval-augmented wrappers that summarize
            the top 5 links. SCAR was architected from the ground up as a self-correcting agent.
          </p>
        </div>

        {/* Table Container */}
        <div
          className="landing-card"
          style={{
            overflow: "hidden",
            border: "1px solid var(--border)",
            background: "rgba(18, 18, 24, 0.8)",
          }}
        >
          <div style={{ overflowX: "auto" }}>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                textAlign: "left",
                minWidth: 640,
              }}
            >
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)", background: "rgba(255, 255, 255, 0.02)" }}>
                  <th
                    style={{
                      padding: "18px 24px",
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      width: "25%",
                    }}
                  >
                    Capability
                  </th>
                  <th
                    style={{
                      padding: "18px 24px",
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      color: "#94a3b8",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      width: "35%",
                    }}
                  >
                    Standard Single-Shot RAG
                  </th>
                  <th
                    style={{
                      padding: "18px 24px",
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      color: "var(--accent-ink)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      width: "40%",
                      background: "rgba(139, 92, 246, 0.08)",
                      borderLeft: "1px solid rgba(139, 92, 246, 0.2)",
                    }}
                  >
                    SCAR Autonomous Loop
                  </th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON_ROWS.map((row, idx) => (
                  <tr
                    key={row.feature}
                    style={{
                      borderBottom:
                        idx === COMPARISON_ROWS.length - 1
                          ? "none"
                          : "1px solid var(--border)",
                      transition: "background 0.15s ease",
                    }}
                  >
                    <td
                      style={{
                        padding: "18px 24px",
                        fontSize: "0.9rem",
                        fontWeight: 700,
                        color: "var(--text-primary)",
                        verticalAlign: "top",
                      }}
                    >
                      {row.feature}
                    </td>

                    {/* Standard RAG */}
                    <td
                      style={{
                        padding: "18px 24px",
                        fontSize: "0.85rem",
                        color: "var(--text-muted)",
                        verticalAlign: "top",
                        lineHeight: 1.5,
                      }}
                    >
                      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                        <X
                          size={16}
                          style={{
                            color: "#ef4444",
                            flexShrink: 0,
                            marginTop: 2,
                          }}
                        />
                        <span>{row.rag}</span>
                      </div>
                    </td>

                    {/* SCAR */}
                    <td
                      style={{
                        padding: "18px 24px",
                        fontSize: "0.88rem",
                        color: "var(--text-primary)",
                        verticalAlign: "top",
                        lineHeight: 1.5,
                        background: "rgba(139, 92, 246, 0.04)",
                        borderLeft: "1px solid rgba(139, 92, 246, 0.2)",
                      }}
                    >
                      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                        <Check
                          size={16}
                          style={{
                            color: "#10b981",
                            flexShrink: 0,
                            marginTop: 2,
                          }}
                        />
                        <span>{row.scar}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
