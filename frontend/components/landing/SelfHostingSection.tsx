"use client";

import React, { useState } from "react";
import { Check, Copy, Server, Terminal } from "lucide-react";

const DOCKER_SNIPPET = `# 1. Clone the repository
git clone https://github.com/a-k-s-0-1/scar.ai.git
cd scar.ai

# 2. Configure environment credentials
cp .env.example .env
# Edit .env and supply TAVILY_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

# 3. Spin up full stack (FastAPI + Next.js + Postgres + Redis)
docker compose up -d --build

# 4. Open browser at http://localhost:3000`;

export function SelfHostingSection() {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(DOCKER_SNIPPET);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section id="self-hosting" style={{ padding: "80px 0", borderTop: "1px solid var(--border)" }}>
      <div className="landing-container">
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="landing-badge" style={{ marginBottom: 12 }}>
            Developer First
          </span>
          <h2
            style={{
              fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: 16,
            }}
          >
            Deploy Anywhere in 60 Seconds
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", lineHeight: 1.6 }}>
            No cloud lock-in. Self-host SCAR on your own hardware, Hetzner, AWS, or DigitalOcean
            with full PostgreSQL, Redis, and WebSocket persistence.
          </p>
        </div>

        {/* Code Terminal Box */}
        <div
          className="landing-card"
          style={{
            maxWidth: 780,
            margin: "0 auto 36px",
            overflow: "hidden",
            background: "rgba(10, 10, 14, 0.95)",
            border: "1px solid rgba(255, 255, 255, 0.12)",
          }}
        >
          {/* Terminal Window Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 18px",
              background: "rgba(255, 255, 255, 0.03)",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ef4444" }} />
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#f59e0b" }} />
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#10b981" }} />
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  marginLeft: 10,
                  fontSize: "0.74rem",
                  color: "var(--text-muted)",
                  fontFamily: "var(--font-mono)",
                }}
              >
                <Terminal size={13} />
                <span>bash — docker-compose</span>
              </div>
            </div>

            <button
              type="button"
              onClick={handleCopy}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 10px",
                borderRadius: 6,
                background: copied ? "rgba(16, 185, 129, 0.15)" : "rgba(255, 255, 255, 0.05)",
                border: copied ? "1px solid #10b981" : "1px solid var(--border)",
                color: copied ? "#10b981" : "var(--text-secondary)",
                fontSize: "0.74rem",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
              title="Copy shell snippet to clipboard"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>

          {/* Terminal Content */}
          <pre
            style={{
              margin: 0,
              padding: "20px 24px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.86rem",
              lineHeight: 1.65,
              color: "#e2e8f0",
              overflowX: "auto",
            }}
          >
            <code>{DOCKER_SNIPPET}</code>
          </pre>
        </div>

        {/* Feature Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 20,
            maxWidth: 960,
            margin: "0 auto",
          }}
        >
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Server size={18} style={{ color: "var(--accent-ink)", flexShrink: 0, marginTop: 3 }} />
            <div>
              <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Zero External Vector Lock-In
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                Stores propositions and graph topologies in standard relational tables with asyncpg.
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Server size={18} style={{ color: "#38bdf8", flexShrink: 0, marginTop: 3 }} />
            <div>
              <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Full WebSocket Streaming
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                Live bi-directional telemetry keeps clients informed without polling.
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <Server size={18} style={{ color: "#10b981", flexShrink: 0, marginTop: 3 }} />
            <div>
              <div style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Production Security Ready
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.5 }}>
                Protected with X-API-Key middleware, CORS isolation, and environment gating.
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
