"use client";

import React, { useState } from "react";
import Link from "next/link";
import { ArrowRight, Menu, Sparkles, X } from "lucide-react";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

function GithubIcon({ size = 17 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" />
      <path d="M9 18c-4.51 2-5-2-7-2" />
    </svg>
  );
}

export function LandingNavbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Lock body scroll while mobile menu is open
  React.useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileMenuOpen]);

  const navLinks = [
    { label: "Pipeline", href: "#pipeline" },
    { label: "Why SCAR", href: "#comparison" },
    { label: "Architecture", href: "#architecture" },
    { label: "Self-Hosting", href: "#self-hosting" },
    { label: "FAQ", href: "#faq" },
  ];

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 50,
        width: "100%",
        borderBottom: "1px solid var(--border)",
        background: "rgba(15, 15, 19, 0.82)",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
      }}
    >
      <div
        className="landing-container"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: 68,
        }}
      >
        {/* Brand - Clickable logo */}
        <Link
          href="/"
          aria-label="SCAR — Self-Correcting Agent for Research Home"
          title="SCAR Home"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            textDecoration: "none",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: 34,
              height: 34,
              borderRadius: 10,
              background: "linear-gradient(135deg, #8b5cf6, #3b82f6)",
              color: "#ffffff",
              boxShadow: "0 0 16px rgba(139, 92, 246, 0.4)",
            }}
          >
            <Sparkles size={18} aria-hidden="true" />
          </span>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span
                style={{
                  fontSize: "1.1rem",
                  fontWeight: 800,
                  letterSpacing: "-0.02em",
                  color: "#ffffff",
                }}
              >
                SCAR
              </span>
              <span
                style={{
                  fontSize: "0.62rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  padding: "2px 6px",
                  borderRadius: 4,
                  background: "rgba(139, 92, 246, 0.2)",
                  color: "#c4b5fd",
                  border: "1px solid rgba(139, 92, 246, 0.3)",
                }}
              >
                Agent v1
              </span>
            </div>
            <span
              style={{
                display: "block",
                fontSize: "0.68rem",
                color: "var(--text-muted)",
                lineHeight: 1.2,
              }}
            >
              Self-Correcting Agent for Research
            </span>
          </div>
        </Link>

        {/* Desktop Navigation */}
        <nav
          aria-label="Main"
          className="landing-nav-desktop"
        >
          <ul
            style={{
              display: "flex",
              alignItems: "center",
              gap: 28,
              listStyle: "none",
              margin: 0,
              padding: 0,
            }}
          >
            {navLinks.map((item) => (
              <li key={item.label}>
                <a
                  href={item.href}
                  style={{
                    fontSize: "0.85rem",
                    color: "var(--text-secondary)",
                    textDecoration: "none",
                    fontWeight: 500,
                    transition: "color 0.15s ease",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.color = "var(--text-primary)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.color = "var(--text-secondary)")
                  }
                >
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        {/* Action Buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <a
            href="https://github.com/a-k-s-0-1/scar.ai"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              alignItems: "center",
              justifyContent: "center",
              width: 36,
              height: 36,
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "rgba(255, 255, 255, 0.03)",
              color: "var(--text-secondary)",
              transition: "all 0.15s ease",
            }}
            className="landing-github-btn"
            aria-label="GitHub Repository"
            title="GitHub Repository"
          >
            <GithubIcon size={17} />
          </a>

          <div className="landing-nav-desktop" style={{ display: "flex", alignItems: "center" }}>
            <ThemeToggle />
          </div>

          <Link
            href="/app"
            className="btn-glow"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "9px 18px",
              fontSize: "0.86rem",
              fontWeight: 600,
              textDecoration: "none",
              borderRadius: 10,
            }}
          >
            <span>Launch Webapp</span>
            <ArrowRight size={15} aria-hidden="true" />
          </Link>

          {/* Mobile Menu Toggle */}
          <button
            type="button"
            className="icon-button landing-mobile-toggle"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile Backdrop & Drawer */}
      {mobileMenuOpen && (
        <>
          <div
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Close menu"
            style={{
              position: "fixed",
              top: 68,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0, 0, 0, 0.6)",
              backdropFilter: "blur(4px)",
              WebkitBackdropFilter: "blur(4px)",
              zIndex: 40,
            }}
          />
          <div
            style={{
              position: "relative",
              zIndex: 50,
              borderTop: "1px solid var(--border)",
              background: "var(--bg-surface)",
              padding: "20px 24px 28px",
              display: "flex",
              flexDirection: "column",
              gap: 16,
              boxShadow: "0 20px 40px rgba(0, 0, 0, 0.4)",
              maxHeight: "calc(100vh - 68px)",
              overflowY: "auto",
            }}
          >
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              {navLinks.map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      fontSize: "0.96rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      textDecoration: "none",
                      padding: "10px 12px",
                      borderRadius: 8,
                      background: "var(--bg-subtle)",
                      transition: "background 0.15s ease",
                    }}
                  >
                    <span>{item.label}</span>
                    <ArrowRight size={14} style={{ color: "var(--text-muted)" }} aria-hidden="true" />
                  </a>
                </li>
              ))}
            </ul>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                paddingTop: 12,
                borderTop: "1px solid var(--border)",
              }}
            >
              <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                Theme Appearance
              </span>
              <ThemeToggle />
            </div>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 0",
              }}
            >
              <a
                href="https://github.com/a-k-s-0-1/scar.ai"
                target="_blank"
                rel="noopener noreferrer"
                onClick={() => setMobileMenuOpen(false)}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: "0.85rem",
                  color: "var(--text-secondary)",
                  textDecoration: "none",
                  fontWeight: 500,
                }}
              >
                <GithubIcon size={16} />
                <span>GitHub Source</span>
              </a>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>v1.0.0</span>
            </div>

            <div style={{ paddingTop: 8, borderTop: "1px solid var(--border)" }}>
              <Link
                href="/app"
                onClick={() => setMobileMenuOpen(false)}
                className="btn-glow"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  padding: "12px",
                  width: "100%",
                  textDecoration: "none",
                  fontWeight: 600,
                  fontSize: "0.92rem",
                  borderRadius: 10,
                }}
              >
                <span>Launch Research Console</span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
          </div>
        </>
      )}
    </header>
  );
}
