import React from "react";
import Link from "next/link";
import { ArrowRight, Brain, Home, Sparkles } from "lucide-react";

export const metadata = {
  title: "404 — Page Not Found",
  description: "The requested trajectory or knowledge node does not exist in SCAR.",
};

export default function NotFound() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-primary)",
        color: "var(--text-primary)",
        overflowX: "hidden",
      }}
    >
      {/* Top Header */}
      <header
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-header)",
          backdropFilter: "blur(16px)",
          padding: "16px 24px",
        }}
      >
        <div
          style={{
            maxWidth: 1100,
            margin: "0 auto",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Link
            href="/"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              textDecoration: "none",
            }}
            aria-label="Return to SCAR Home"
          >
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 32,
                height: 32,
                borderRadius: 8,
                background: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
                color: "#ffffff",
                boxShadow: "0 0 14px rgba(139, 92, 246, 0.4)",
              }}
            >
              <Sparkles size={16} aria-hidden="true" />
            </span>
            <span
              style={{
                fontSize: "1.05rem",
                fontWeight: 800,
                color: "var(--text-primary)",
                letterSpacing: "-0.02em",
              }}
            >
              SCAR
            </span>
          </Link>

          <Link
            href="/app"
            className="btn-glow"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "7px 14px",
              fontSize: "0.82rem",
              fontWeight: 600,
              textDecoration: "none",
              borderRadius: 8,
            }}
          >
            <span>Research Console</span>
            <ArrowRight size={14} aria-hidden="true" />
          </Link>
        </div>
      </header>

      {/* Main 404 Hero */}
      <main
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px 20px",
        }}
      >
        <div
          className="landing-card"
          style={{
            maxWidth: 580,
            width: "100%",
            textAlign: "center",
            padding: "48px 32px",
            border: "1px solid var(--accent-border)",
            boxShadow: "0 20px 50px rgba(0,0,0,0.3), 0 0 30px var(--accent-soft)",
            position: "relative",
          }}
        >
          {/* Badge */}
          <div style={{ marginBottom: 16 }}>
            <span className="landing-badge">
              <Brain size={14} aria-hidden="true" />
              <span>Uncharted Trajectory</span>
            </span>
          </div>

          {/* 404 Glitch Number */}
          <div
            className="mono-num"
            style={{
              fontSize: "clamp(4.5rem, 12vw, 7.5rem)",
              fontWeight: 900,
              lineHeight: 1,
              letterSpacing: "-0.05em",
              background: "linear-gradient(135deg, var(--accent) 0%, #38bdf8 100%)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              marginBottom: 12,
            }}
          >
            404
          </div>

          <h1
            style={{
              fontSize: "clamp(1.3rem, 3vw, 1.7rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              color: "var(--text-primary)",
              marginBottom: 12,
            }}
          >
            Knowledge Node Not Found
          </h1>

          <p
            style={{
              fontSize: "0.92rem",
              color: "var(--text-secondary)",
              lineHeight: 1.6,
              marginBottom: 32,
              maxWidth: 440,
              marginLeft: "auto",
              marginRight: "auto",
            }}
          >
            The route or resource you are looking for has not been mapped into SCAR&apos;s
            knowledge graph. It may have been relocated or purged.
          </p>

          {/* Action Buttons */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              flexWrap: "wrap",
              marginBottom: 32,
            }}
          >
            <Link
              href="/"
              className="btn-secondary"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "11px 20px",
                fontSize: "0.88rem",
                fontWeight: 600,
                textDecoration: "none",
                borderRadius: 10,
              }}
            >
              <Home size={15} aria-hidden="true" />
              <span>Back to Home</span>
            </Link>

            <Link
              href="/app"
              className="btn-glow"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "11px 22px",
                fontSize: "0.88rem",
                fontWeight: 600,
                textDecoration: "none",
                borderRadius: 10,
              }}
            >
              <Sparkles size={15} aria-hidden="true" />
              <span>Launch Webapp</span>
            </Link>
          </div>

          {/* Quick Links */}
          <div
            style={{
              borderTop: "1px solid var(--border)",
              paddingTop: 20,
              fontSize: "0.78rem",
              color: "var(--text-muted)",
            }}
          >
            <span style={{ display: "block", marginBottom: 10, fontWeight: 600 }}>
              Popular Destinations:
            </span>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 16,
                flexWrap: "wrap",
              }}
            >
              <Link
                href="/#pipeline"
                style={{ color: "var(--accent-ink)", textDecoration: "none", fontWeight: 500 }}
              >
                6-Step Pipeline
              </Link>
              <span>•</span>
              <Link
                href="/#architecture"
                style={{ color: "var(--accent-ink)", textDecoration: "none", fontWeight: 500 }}
              >
                Model Architecture
              </Link>
              <span>•</span>
              <Link
                href="/#faq"
                style={{ color: "var(--accent-ink)", textDecoration: "none", fontWeight: 500 }}
              >
                FAQ & Help
              </Link>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer
        style={{
          borderTop: "1px solid var(--border)",
          padding: "16px 24px",
          textAlign: "center",
          fontSize: "0.75rem",
          color: "var(--text-muted)",
        }}
      >
        © {new Date().getFullYear()} SCAR • Self-Correcting Agent for Research
      </footer>
    </div>
  );
}
