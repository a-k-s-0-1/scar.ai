"use client";

import React, { useState } from "react";
import { AlertTriangle, Brain, Play, Search, Sparkles, Zap } from "lucide-react";
import { startResearch } from "../../lib/api";
import { useDefaultDepth } from "../../lib/preferences";
import { LinearProgress } from "../ui/Progress";
import type { DepthLevel, ResearchSession, StartResearchRequest } from "../../lib/types";

interface ResearchFormProps {
  onStart: (session: ResearchSession) => void;
  initialQuestion?: string;
}

const DEPTH_OPTIONS: {
  value: DepthLevel;
  label: string;
  description: string;
  iterations: string;
  Icon: React.ComponentType<{ size?: number }>;
}[] = [
  {
    value: "shallow",
    label: "Quick",
    description: "3 iterations, rapid overview",
    iterations: "~3 min",
    Icon: Zap,
  },
  {
    value: "standard",
    label: "Standard",
    description: "5 iterations, balanced depth",
    iterations: "~5 min",
    Icon: Search,
  },
  {
    value: "deep",
    label: "Deep",
    description: "8 iterations, thorough analysis",
    iterations: "~8 min",
    Icon: Brain,
  },
];

export function ResearchForm({ onStart, initialQuestion = "" }: ResearchFormProps) {
  const { depth: defaultDepth } = useDefaultDepth();
  const [question, setQuestion] = useState(initialQuestion);
  // Null until the user picks a depth: the stored default wins until then, and
  // the store re-renders us once hydration reveals it.
  const [depthOverride, setDepthOverride] = useState<DepthLevel | null>(null);
  const depth: DepthLevel = depthOverride ?? defaultDepth;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [charCount, setCharCount] = useState(initialQuestion.length);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || loading) return;

    setLoading(true);
    setError(null);

    try {
      const body: StartResearchRequest = {
        question: question.trim(),
        depth,
        min_sources_required: depth === "shallow" ? 5 : depth === "standard" ? 10 : 20,
        // Must stay within the API's 1-10 minute ceiling; the iteration caps
        // (3/5/8) usually bind first, this is the safety net.
        max_research_time_minutes:
          depth === "shallow" ? 5 : depth === "standard" ? 8 : 10,
      };
      const session = await startResearch(body);
      onStart(session);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start research. Is the backend running?"
      );
    } finally {
      setLoading(false);
    }
  };

  const handleQuestionChange = (val: string) => {
    setQuestion(val);
    setCharCount(val.length);
    if (error) setError(null);
  };

  return (
    <div style={{ width: "100%" }}>
      {/* Hero header */}
      <div style={{ textAlign: "center", marginBottom: 32 }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 16px",
            borderRadius: 20,
            background: "var(--accent-soft)",
            border: "1px solid var(--accent-border)",
            marginBottom: 20,
            color: "var(--accent-ink)",
          }}
        >
          <Sparkles size={15} aria-hidden="true" />
          <span
            style={{
              fontSize: "0.78rem",
              fontWeight: 600,
              letterSpacing: "0.04em",
            }}
          >
            Self-Correcting AI Research Agent
          </span>
        </div>

        <h2
          style={{
            fontSize: "clamp(1.9rem, 4.6vw, 2.75rem)",
            fontWeight: 800,
            lineHeight: 1.1,
            marginBottom: 14,
            letterSpacing: "-0.02em",
          }}
        >
          <span className="gradient-text">Ask anything.</span>
          <br />
          <span style={{ color: "var(--text-primary)" }}>We&apos;ll research it.</span>
        </h2>

        <p
          style={{
            color: "var(--text-secondary)",
            fontSize: "1rem",
            maxWidth: 480,
            margin: "0 auto",
            lineHeight: 1.6,
          }}
        >
          Multi-source search, claim extraction, contradiction detection, and
          evidence-grounded reports — automatically.
        </p>
      </div>

      {/* Form card */}
      <form onSubmit={handleSubmit}>
        <div
          className="card"
          style={{ padding: "26px 26px 22px", marginBottom: 16 }}
        >
          {/* Question input */}
          <div style={{ marginBottom: 20 }}>
            <label
              htmlFor="question"
              style={{
                display: "block",
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "var(--text-secondary)",
                marginBottom: 8,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
              }}
            >
              Research Question
            </label>
            <div style={{ position: "relative" }}>
              <textarea
                id="question"
                className="input-field"
                placeholder="e.g. What are the latest breakthroughs in quantum computing?"
                value={question}
                onChange={(e) => handleQuestionChange(e.target.value)}
                maxLength={500}
                rows={3}
                required
                style={{ resize: "vertical", minHeight: 88 }}
                disabled={loading}
              />
              <span
                className="mono-num"
                style={{
                  position: "absolute",
                  bottom: 10,
                  right: 14,
                  fontSize: "0.68rem",
                  color: charCount > 400 ? "var(--warn)" : "var(--text-muted)",
                }}
              >
                {charCount}/500
              </span>
            </div>
          </div>

          {/* Depth selector */}
          <div style={{ marginBottom: 8 }}>
            <span
              style={{
                display: "block",
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "var(--text-secondary)",
                marginBottom: 10,
                letterSpacing: "0.04em",
                textTransform: "uppercase",
              }}
            >
              Research Depth
            </span>
            <div className="depth-grid">
              {DEPTH_OPTIONS.map((opt) => {
                const selected = depth === opt.value;
                const { Icon } = opt;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDepthOverride(opt.value)}
                    disabled={loading}
                    aria-pressed={selected}
                    style={{
                      padding: "12px 10px",
                      borderRadius: 12,
                      border: selected
                        ? "1px solid var(--accent-border)"
                        : "1px solid var(--border)",
                      background: selected ? "var(--accent-soft)" : "var(--bg-subtle)",
                      cursor: loading ? "not-allowed" : "pointer",
                      textAlign: "center",
                      fontFamily: "inherit",
                      transition: "all 0.15s ease",
                      opacity: loading ? 0.5 : 1,
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        display: "flex",
                        justifyContent: "center",
                        color: selected ? "var(--accent-ink)" : "var(--text-muted)",
                        marginBottom: 6,
                      }}
                    >
                      <Icon size={17} />
                    </span>
                    <span
                      style={{
                        display: "block",
                        fontSize: "0.85rem",
                        fontWeight: 700,
                        color: selected ? "var(--accent-ink)" : "var(--text-primary)",
                        marginBottom: 2,
                      }}
                    >
                      {opt.label}
                    </span>
                    <span
                      style={{
                        display: "block",
                        fontSize: "0.72rem",
                        color: "var(--text-muted)",
                        lineHeight: 1.3,
                      }}
                    >
                      {opt.description}
                    </span>
                    <span
                      className="mono-num"
                      style={{
                        display: "block",
                        fontSize: "0.7rem",
                        color: selected ? "var(--accent-ink)" : "var(--text-muted)",
                        marginTop: 4,
                        fontWeight: 600,
                      }}
                    >
                      {opt.iterations}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div
            className="animate-fade-in-up"
            style={{
              padding: "12px 16px",
              borderRadius: 10,
              background: "var(--danger-soft)",
              border: "1px solid var(--danger-border)",
              color: "var(--danger)",
              fontSize: "0.85rem",
              marginBottom: 12,
              display: "flex",
              gap: 8,
              alignItems: "flex-start",
            }}
          >
            <AlertTriangle size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Loading progress */}
        {loading && (
          <div style={{ marginBottom: 12 }}>
            <LinearProgress value={0.3} animated />
            <p
              style={{
                textAlign: "center",
                color: "var(--text-muted)",
                fontSize: "0.8rem",
                marginTop: 6,
              }}
            >
              Initializing research session…
            </p>
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          className="btn-glow"
          disabled={loading || !question.trim()}
          style={{
            width: "100%",
            padding: "16px",
            fontSize: "1rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
          }}
        >
          {loading ? (
            <>
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span className="typing-dot" />
              <span style={{ marginLeft: 4 }}>Starting…</span>
            </>
          ) : (
            <>
              <Play size={17} aria-hidden="true" />
              <span>Start Research</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
}
