"use client";

import React from "react";
import { Cpu, Database, HardDrive, RefreshCw, ShieldCheck, Zap } from "lucide-react";

export function ArchitectureTopology() {
  const tiers = [
    {
      tier: "Tier 1: Local Edge",
      name: "Local Ollama (Llama 3.2)",
      task: "Zero-Latency Heuristics & Classification",
      color: "#38bdf8",
      icon: HardDrive,
      points: [
        "Runs 100% locally on CPU/GPU via Ollama REST API",
        "Executes query formulation & preliminary topic routing",
        "No network token cost; falls back to Tier 2 if unreachable",
      ],
    },
    {
      tier: "Tier 2: High-Speed Extract",
      name: "Google Gemini 3.8 Flash",
      task: "Proposition Decomposition & Claim Triples",
      color: "#8b5cf6",
      icon: Zap,
      points: [
        "Structured JSON schema enforcement for (S, P, O) claims",
        "High token throughput parses 100+ pages in seconds",
        "Falls back to Tier 3 on provider rate limits",
      ],
    },
    {
      tier: "Tier 3: Deep Reasoning",
      name: "Groq Cloud (GPT-OSS 120B)",
      task: "Contradiction Resolution & Synthesis",
      color: "#10b981",
      icon: Cpu,
      points: [
        "Massive parameter scale handles complex empirical contradictions",
        "Synthesizes cited research reports & identifies known unknowns",
        "Falls back to Gemini Flash with fallback provenance badges",
      ],
    },
  ];

  return (
    <section id="architecture" style={{ padding: "80px 0", borderTop: "1px solid var(--border)" }}>
      <div className="landing-container">
        {/* Header */}
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="landing-badge" style={{ marginBottom: 12 }}>
            Fault-Tolerant Topology
          </span>
          <h2
            style={{
              fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: 16,
            }}
          >
            Multi-Tier Dynamic Model Router
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", lineHeight: 1.6 }}>
            Never fail a research run due to third-party outages or rate limits. SCAR
            routes tasks dynamically across 3 model tiers with automatic cascading fallback.
          </p>
        </div>

        {/* 3 Tier Cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: 20,
            marginBottom: 40,
          }}
        >
          {tiers.map((t) => {
            const Icon = t.icon;
            return (
              <div
                key={t.tier}
                className="landing-card"
                style={{
                  padding: "28px 24px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: 16,
                    }}
                  >
                    <span
                      style={{
                        fontSize: "0.72rem",
                        fontWeight: 700,
                        color: t.color,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      {t.tier}
                    </span>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 8,
                        background: `${t.color}15`,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: t.color,
                      }}
                    >
                      <Icon size={16} />
                    </div>
                  </div>

                  <h3
                    style={{
                      fontSize: "1.2rem",
                      fontWeight: 800,
                      color: "var(--text-primary)",
                      marginBottom: 6,
                    }}
                  >
                    {t.name}
                  </h3>
                  <p
                    style={{
                      fontSize: "0.82rem",
                      color: "var(--text-muted)",
                      fontWeight: 500,
                      marginBottom: 20,
                    }}
                  >
                    {t.task}
                  </p>

                  <ul
                    style={{
                      listStyle: "none",
                      margin: 0,
                      padding: 0,
                      display: "flex",
                      flexDirection: "column",
                      gap: 10,
                    }}
                  >
                    {t.points.map((pt) => (
                      <li
                        key={pt}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 10,
                          fontSize: "0.85rem",
                          color: "var(--text-secondary)",
                          lineHeight: 1.5,
                        }}
                      >
                        <span
                          style={{
                            display: "inline-block",
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: t.color,
                            marginTop: 7,
                            flexShrink: 0,
                          }}
                        />
                        <span>{pt}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          })}
        </div>

        {/* Resilience Badges */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 16,
            padding: "20px 24px",
            borderRadius: 14,
            background: "rgba(255, 255, 255, 0.02)",
            border: "1px solid var(--border)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <ShieldCheck size={20} style={{ color: "#10b981", flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Concurrency Semaphores
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Prevents 429 token limits across concurrent sessions
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <RefreshCw size={20} style={{ color: "#38bdf8", flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Tenacity Exponential Backoff
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Automatic retry policy with jitter on HTTP 429/503
              </div>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Database size={20} style={{ color: "#8b5cf6", flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Startup Reconciliation
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Zero phantom sessions if process restarts mid-loop
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
