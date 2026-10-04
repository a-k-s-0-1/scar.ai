"use client";

import React, { Suspense, useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, Menu, Sparkles } from "lucide-react";
import { ResearchForm } from "@/components/research/ResearchForm";
import { ResearchDashboard } from "@/components/research/ResearchDashboard";
import { EvaluationDashboard } from "@/components/research/EvaluationDashboard";
import { MemoryPanel } from "@/components/research/MemoryPanel";
import { Sidebar, type AppView } from "@/components/layout/Sidebar";
import { SettingsPanel } from "@/components/panels/SettingsPanel";
import { AboutPanel } from "@/components/panels/AboutPanel";
import { useResearchSocket } from "@/lib/useResearchSocket";
import { sanitizeSearchQuery } from "@/lib/sanitize";
import type { ResearchSession } from "@/lib/types";

const VIEW_TITLES: Record<AppView, string> = {
  home: "New research",
  research: "Investigation",
  evaluation: "RL evaluation",
  memory: "Long-term memory",
  settings: "Settings",
  about: "About",
};

function ResearchConsoleInner() {
  const searchParams = useSearchParams();
  const initialQuery = useMemo(() => {
    const raw = searchParams.get("q");
    return sanitizeSearchQuery(raw);
  }, [searchParams]);

  const [view, setView] = useState<AppView>("home");
  const [session, setSession] = useState<ResearchSession | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(false);

  const { messages, activity, isConnected, connect, disconnect } =
    useResearchSocket();

  const isDrawerViewport = () =>
    typeof window !== "undefined" &&
    window.matchMedia("(max-width: 1024px)").matches;

  const showMenu = useCallback(() => {
    if (isDrawerViewport()) setNavOpen(true);
    else setNavCollapsed(false);
  }, []);

  const hideMenu = useCallback(() => {
    if (isDrawerViewport()) setNavOpen(false);
    else setNavCollapsed(true);
  }, []);

  const navigate = useCallback(
    (next: AppView) => {
      setNavOpen(false);
      setView(next);
      if (next === "home") {
        disconnect();
        setSession(null);
        setRefreshTrigger((prev) => prev + 1);
      }
    },
    [disconnect]
  );

  const handleResearchStart = useCallback(
    (newSession: ResearchSession) => {
      setSession(newSession);
      setView("research");
      setRefreshTrigger((prev) => prev + 1);
      connect(newSession.id);
    },
    [connect]
  );

  const handleSelectSession = useCallback(
    (selected: ResearchSession) => {
      setSession(selected);
      setView("research");
      setNavOpen(false);
      if (
        selected.status === "running" ||
        selected.status === "initializing"
      ) {
        connect(selected.id);
      } else {
        disconnect();
      }
    },
    [connect, disconnect]
  );

  return (
    <div
      className={`app-shell${navCollapsed ? " nav-collapsed" : ""}${
        navOpen ? " nav-drawer-open" : ""
      }`}
    >
      <Sidebar
        active={view}
        hasSession={session !== null}
        onNavigate={navigate}
        currentSessionId={session?.id}
        onSelectSession={handleSelectSession}
        refreshTrigger={refreshTrigger}
        open={navOpen}
        onClose={hideMenu}
      />

      <div className="app-col">
        <header className="app-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
            <button
              type="button"
              className="icon-button menu-button"
              onClick={showMenu}
              aria-label="Show menu"
              aria-controls="app-sidebar"
              aria-expanded={navOpen}
              title="Show menu"
            >
              <Menu size={18} aria-hidden="true" />
            </button>

            <div style={{ minWidth: 0 }}>
              <span
                style={{
                  display: "block",
                  fontSize: "0.66rem",
                  fontWeight: 700,
                  letterSpacing: "0.09em",
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                }}
              >
                Self-Correcting Agent for Research - SCAR
              </span>
              <h1
                style={{
                  fontSize: "1rem",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.01em",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {VIEW_TITLES[view]}
              </h1>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Link
              href="/"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: "0.78rem",
                color: "var(--text-muted)",
                textDecoration: "none",
                padding: "6px 12px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "rgba(255,255,255,0.02)",
                transition: "all 0.15s ease",
              }}
              title="Return to SCAR Overview & Documentation"
            >
              <ArrowLeft size={13} aria-hidden="true" />
              <span>Overview</span>
            </Link>
          </div>
        </header>

        <main className="app-main">
          {view === "home" && (
            <div className="main-narrow">
              <ResearchForm
                key={initialQuery}
                onStart={handleResearchStart}
                initialQuestion={initialQuery}
              />
            </div>
          )}

          {view === "research" &&
            (session ? (
              <ResearchDashboard
                session={session}
                messages={messages}
                activity={activity}
                isConnected={isConnected}
                onReset={() => navigate("home")}
                onStartSession={handleResearchStart}
              />
            ) : (
              <div
                className="card main-narrow"
                style={{
                  padding: "32px 28px",
                  textAlign: "center",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem" }}>
                  No investigation is open. Start a new question or pick one from
                  the past investigations list.
                </p>
                <button
                  type="button"
                  className="btn-glow"
                  onClick={() => navigate("home")}
                  style={{ padding: "10px 18px", fontSize: "0.85rem" }}
                >
                  <Sparkles size={15} aria-hidden="true" />
                  Start a new research
                </button>
              </div>
            ))}

          {view === "evaluation" && (
            <div className="main-narrow">
              <EvaluationDashboard />
            </div>
          )}

          {view === "memory" && (
            <div className="main-narrow">
              <MemoryPanel sessionId={session?.id} />
            </div>
          )}

          {view === "settings" && (
            <div className="main-narrow">
              <SettingsPanel />
            </div>
          )}

          {view === "about" && (
            <div className="main-narrow">
              <AboutPanel />
            </div>
          )}
        </main>

        <footer className="app-footer">
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
            Self-Correcting Agent for Research - SCAR · IKF Knowledge Fusion × JEV Decision
            Engine
          </p>
          <button
            type="button"
            onClick={() => navigate("about")}
            style={{
              background: "none",
              border: "none",
              color: "var(--accent-ink)",
              fontSize: "0.75rem",
              fontWeight: 600,
              cursor: "pointer",
              padding: 0,
            }}
          >
            Technology stack
          </button>
        </footer>
      </div>
    </div>
  );
}

export default function AppConsolePage() {
  return (
    <Suspense
      fallback={
        <div
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--text-muted)",
            fontSize: "0.88rem",
          }}
        >
          Initializing SCAR Research Console...
        </div>
      }
    >
      <ResearchConsoleInner />
    </Suspense>
  );
}
