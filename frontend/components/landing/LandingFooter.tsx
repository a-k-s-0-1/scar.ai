"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import DitheredFooter from "@/components/ui/dithered-footer";

export function LandingFooter() {
  return (
    <>
      {/* Call to action pre-footer banner */}
      <section
        style={{
          padding: "60px 0 20px",
          background: "transparent",
        }}
      >
        <div className="landing-container">
          <div
            className="landing-card"
            style={{
              padding: "48px 32px",
              textAlign: "center",
              background: "linear-gradient(135deg, rgba(155, 113, 178, 0.16) 0%, rgba(56, 189, 248, 0.08) 100%)",
              border: "1px solid rgba(155, 113, 178, 0.35)",
              boxShadow: "0 20px 50px rgba(0,0,0,0.5), 0 0 30px rgba(155, 113, 178, 0.15)",
            }}
          >
            <span className="landing-badge" style={{ marginBottom: 14 }}>
              Experience Next-Generation AI Research
            </span>
            <h3
              style={{
                fontSize: "clamp(1.6rem, 3vw, 2.2rem)",
                fontWeight: 800,
                letterSpacing: "-0.02em",
                marginBottom: 12,
              }}
            >
              Ready to explore the frontier of autonomous discovery?
            </h3>
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "1rem",
                maxWidth: 620,
                margin: "0 auto 28px",
                lineHeight: 1.6,
              }}
            >
              Launch the research console, input your most demanding scientific or technical query,
              and watch SCAR synthesize verifiable findings in real-time.
            </p>

            <Link
              href="/app"
              className="btn-glow"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
                padding: "14px 28px",
                fontSize: "1rem",
                fontWeight: 700,
                borderRadius: 12,
                textDecoration: "none",
              }}
            >
              <span>Launch SCAR Research Console</span>
              <ArrowRight size={17} />
            </Link>
          </div>
        </div>
      </section>

      {/* Dithered Footer with custom animated dot matrix & brand highlight */}
      <DitheredFooter
        brand="S.C.A.R."
        brandHref="/"
        tagline="Self-Correcting Agent for Research • Iterative Knowledge Fusion & Autonomous Verification."
        accent="#9b71b2"
        onSubscribe={async (email) => {
          // Simulation of newsletter / release alert subscription
          await new Promise((resolve) => setTimeout(resolve, 600));
          console.log("Subscribed email:", email);
        }}
      />
    </>
  );
}

export default LandingFooter;
