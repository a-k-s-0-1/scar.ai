"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";

interface FaqItem {
  q: string;
  a: string;
}

const FAQS: FaqItem[] = [
  {
    q: "How does SCAR eliminate hallucinations?",
    a: "Unlike traditional LLM workflows that generate summaries directly from long, fuzzy context windows, SCAR enforces strict proposition extraction. Every claim is decomposed into an atomic (Subject, Predicate, Object) triple that is permanently linked to its source document ID and verified with domain credibility scoring. If an assertion cannot be grounded in an extracted proposition, it is rejected.",
  },
  {
    q: "What is Iterative Knowledge Fusion (IKF)?",
    a: "IKF is SCAR's dynamic knowledge graph builder. As each research iteration discovers new sources and propositions, IKF performs canonical entity resolution, mapping concepts into graph nodes and relationships into directed, weighted edges. When multiple independent sources confirm a relationship, its edge weight increases, providing measurable conviction.",
  },
  {
    q: "What is the Judgment Evaluation Vector (JEV)?",
    a: "JEV is the autonomous decision policy governing the research loop. Rather than terminating arbitrarily, JEV tracks knowledge coverage using an asymptotic saturation formula: 1 - exp(-1.6 * ratio). It calculates novelty across consecutive iterations. If novelty drops below a threshold across consecutive cycles while coverage exceeds targets, JEV triggers a STOP action to write the report; otherwise, it triggers query expansion to fill gaps.",
  },
  {
    q: "Can I run SCAR completely offline using local models?",
    a: "Yes! SCAR features a Tier 1 local router that connects to any Ollama or vLLM endpoint (such as Llama 3.2, Mistral, or Qwen). By configuring OLLAMA_BASE_URL in your .env file, query classification, proposition extraction, and contradiction checks can be executed entirely on-premise without external API keys.",
  },
  {
    q: "How does SCAR handle vendor rate limits and 429 errors?",
    a: "SCAR uses a shared concurrency semaphore across active sessions to prevent quota spikes. Every external API call is wrapped in a Tenacity exponential backoff handler with randomized jitter. If a provider remains exhausted or suffers an outage, the multi-tier router automatically cascades to secondary providers (e.g. Groq GPT-OSS 120B to Gemini 3.8 Flash), logging fallback provenance tags.",
  },
];

export function FaqSection() {
  const [openIdx, setOpenIdx] = useState<number | null>(0);

  const toggle = (idx: number) => {
    setOpenIdx(openIdx === idx ? null : idx);
  };

  return (
    <section id="faq" style={{ padding: "80px 0", borderTop: "1px solid var(--border)" }}>
      <div className="landing-container">
        {/* Header */}
        <div style={{ textAlign: "center", maxWidth: 720, margin: "0 auto 50px" }}>
          <span className="landing-badge" style={{ marginBottom: 12 }}>
            Technical Clarity
          </span>
          <h2
            style={{
              fontSize: "clamp(1.8rem, 3.5vw, 2.6rem)",
              fontWeight: 800,
              letterSpacing: "-0.02em",
              marginBottom: 16,
            }}
          >
            Frequently Asked Questions
          </h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "1.05rem", lineHeight: 1.6 }}>
            Everything you need to know about the algorithms, mathematical models, and
            architectural guarantees behind SCAR.
          </p>
        </div>

        {/* Accordion */}
        <div
          style={{
            maxWidth: 780,
            margin: "0 auto",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          {FAQS.map((faq, idx) => {
            const isOpen = openIdx === idx;
            return (
              <div
                key={faq.q}
                className="landing-card"
                style={{
                  borderRadius: 14,
                  overflow: "hidden",
                  border: isOpen
                    ? "1px solid rgba(139, 92, 246, 0.4)"
                    : "1px solid var(--border)",
                  background: isOpen
                    ? "rgba(22, 22, 32, 0.9)"
                    : "rgba(18, 18, 24, 0.6)",
                  transition: "all 0.2s ease",
                }}
              >
                <button
                  type="button"
                  onClick={() => toggle(idx)}
                  style={{
                    width: "100%",
                    padding: "20px 24px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "none",
                    border: "none",
                    textAlign: "left",
                    color: "var(--text-primary)",
                    cursor: "pointer",
                    fontSize: "1.02rem",
                    fontWeight: 700,
                  }}
                  aria-expanded={isOpen}
                >
                  <span style={{ paddingRight: 16 }}>{faq.q}</span>
                  <ChevronDown
                    size={18}
                    style={{
                      transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
                      transition: "transform 0.2s ease",
                      color: isOpen ? "var(--accent-ink)" : "var(--text-muted)",
                      flexShrink: 0,
                    }}
                  />
                </button>

                {isOpen && (
                  <div
                    style={{
                      padding: "0 24px 20px",
                      fontSize: "0.92rem",
                      color: "var(--text-secondary)",
                      lineHeight: 1.7,
                      borderTop: "1px solid rgba(255, 255, 255, 0.04)",
                      paddingTop: 16,
                    }}
                  >
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
