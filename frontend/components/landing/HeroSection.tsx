"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  Layers,
  Network,
  Search,
  Zap,
} from "lucide-react";
import { sanitizeSearchQuery } from "@/lib/sanitize";
import PathDrawingPortfolioHero from "@/components/ui/path-drawing-portfolio-hero";

const SAMPLE_PROMPTS = [
  "Nanotech in targeted oncology drug delivery",
  "Solid-state vs lithium-sulfur battery energy density",
  "Post-quantum lattice-based cryptography standards",
  "CRISPR-Cas9 off-target detection algorithms",
];

export function HeroSection() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const handleLaunch = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = sanitizeSearchQuery(query);
    if (clean) {
      router.push(`/app?q=${encodeURIComponent(clean)}`);
    } else {
      router.push("/app");
    }
  };

  const handleSelectSample = (sample: string) => {
    const clean = sanitizeSearchQuery(sample);
    router.push(`/app?q=${encodeURIComponent(clean)}`);
  };

  return (
    <section
      style={{
        position: "relative",
        paddingTop: "40px",
        paddingBottom: "80px",
        overflow: "hidden",
      }}
      className="landing-grid-bg"
    >
      <div className="landing-hero-glow" aria-hidden="true" />

      {/* Path Drawing Animated Showcase */}
      <PathDrawingPortfolioHero
        brand="S.C.A.R."
        tagline="Research that doesn't hallucinate. It self-corrects via Iterative Knowledge Fusion (IKF) & JEV Policy."
        eyebrow="AUTONOMOUS CLOSED-LOOP RESEARCH"
        fromColor="#cda9e2"
        toColor="#9b71b2"
        className="min-h-[auto] pb-4 pt-6"
      >
        <div className="landing-container" style={{ position: "relative", zIndex: 1, width: "100%" }}>
          <div style={{ textAlign: "center", maxWidth: 840, margin: "0 auto" }}>
            {/* Interactive Search Launcher */}
            <div
              className="landing-card"
              style={{
                padding: "8px 8px 8px 18px",
                display: "flex",
                alignItems: "center",
                gap: 12,
                maxWidth: 680,
                margin: "0 auto 20px",
                background: "rgba(20, 20, 26, 0.85)",
                border: "1px solid rgba(155, 113, 178, 0.35)",
                boxShadow: "0 10px 30px rgba(0, 0, 0, 0.5), 0 0 24px rgba(155, 113, 178, 0.18)",
              }}
            >
              <Search size={18} style={{ color: "var(--accent-ink)", flexShrink: 0 }} />
              <form onSubmit={handleLaunch} style={{ flex: 1, display: "flex", alignItems: "center" }}>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Enter any scientific, technological, or market query..."
                  suppressHydrationWarning
                  style={{
                    width: "100%",
                    background: "transparent",
                    border: "none",
                    outline: "none",
                    color: "var(--text-primary)",
                    fontSize: "0.95rem",
                    fontFamily: "inherit",
                  }}
                />
                <button
                  type="submit"
                  className="btn-glow"
                  style={{
                    padding: "10px 20px",
                    fontSize: "0.88rem",
                    fontWeight: 600,
                    whiteSpace: "nowrap",
                    flexShrink: 0,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <span>Run Research</span>
                  <ArrowRight size={15} />
                </button>
              </form>
            </div>

            {/* Sample Prompts Pills */}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                marginBottom: 50,
              }}
            >
              <span style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginRight: 4 }}>
                Try an example:
              </span>
              {SAMPLE_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => handleSelectSample(prompt)}
                  style={{
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid var(--border)",
                    borderRadius: 9999,
                    padding: "5px 12px",
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = "var(--accent-border)";
                    e.currentTarget.style.color = "var(--text-primary)";
                    e.currentTarget.style.background = "var(--accent-soft)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = "var(--border)";
                    e.currentTarget.style.color = "var(--text-secondary)";
                    e.currentTarget.style.background = "rgba(255, 255, 255, 0.03)";
                  }}
                >
                  {prompt}
                </button>
              ))}
            </div>

            {/* Live Preview Mockup Card */}
            <div
              className="landing-card"
              style={{
                padding: "24px 28px",
                textAlign: "left",
                maxWidth: 900,
                margin: "0 auto",
                border: "1px solid rgba(227, 208, 234, 0.16)",
                background: "rgba(15, 15, 22, 0.75)",
              }}
            >
              {/* Mock Header */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingBottom: 16,
                  borderBottom: "1px solid var(--border)",
                  marginBottom: 20,
                  flexWrap: "wrap",
                  gap: 10,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span
                    style={{
                      display: "inline-block",
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: "#10b981",
                      boxShadow: "0 0 10px #10b981",
                    }}
                    aria-hidden="true"
                  />
                  <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#e2e8f0" }}>
                    Autonomous Session #4928 • Nanotech in Targeted Biotech Delivery
                  </span>
                </div>
                <span className="badge badge-purple" style={{ fontSize: "0.72rem" }}>
                  JEV Policy: Plateau Detected → STOP (82% Coverage)
                </span>
              </div>

              {/* Mock Telemetry Stats Grid */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                  gap: 12,
                  marginBottom: 20,
                }}
              >
                {[
                  { label: "Sources Vetted", val: "24", icon: Search, col: "#38bdf8" },
                  { label: "Claims Extracted", val: "93", icon: Layers, col: "#8b5cf6" },
                  { label: "KG Nodes Mapped", val: "118", icon: Network, col: "#a855f7" },
                  { label: "Contradictions", val: "2 Flagged", icon: Zap, col: "#f59e0b" },
                  { label: "Asymptotic Coverage", val: "82.4%", icon: CheckCircle2, col: "#10b981" },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    style={{
                      padding: "12px 14px",
                      borderRadius: 10,
                      background: "rgba(255, 255, 255, 0.02)",
                      border: "1px solid var(--border)",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        fontSize: "0.7rem",
                        color: "var(--text-muted)",
                        marginBottom: 4,
                      }}
                    >
                      <stat.icon size={12} style={{ color: stat.col }} />
                      <span>{stat.label}</span>
                    </div>
                    <div
                      className="mono-num"
                      style={{ fontSize: "1.2rem", fontWeight: 800, color: stat.col }}
                    >
                      {stat.val}
                    </div>
                  </div>
                ))}
              </div>

              {/* Mock Reasoning Callout */}
              <div
                style={{
                  padding: "12px 16px",
                  borderRadius: 10,
                  background: "rgba(155, 113, 178, 0.08)",
                  border: "1px solid rgba(155, 113, 178, 0.25)",
                  fontSize: "0.82rem",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 10,
                  lineHeight: 1.5,
                }}
              >
                <Brain size={16} style={{ color: "var(--accent-ink)", flexShrink: 0, marginTop: 2 }} />
                <div>
                  <strong style={{ color: "var(--text-primary)" }}>
                    Decision Engine (JEV):
                  </strong>{" "}
                  Iteration #3 novelty dropped from 0.52 to 0.14 across consecutive
                  cycles while source coverage reached 82%. Evaluated 2 empirical contradictions
                  regarding lipid nanoparticle kidney toxicity and finalized evidence report with 24
                  citations.
                </div>
              </div>
            </div>
          </div>
        </div>
      </PathDrawingPortfolioHero>
    </section>
  );
}
