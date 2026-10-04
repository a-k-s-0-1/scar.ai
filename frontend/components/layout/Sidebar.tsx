"use client";

import React from "react";
import { Activity, Archive, Brain, Info, Settings, Sparkles, X } from "lucide-react";
import { SessionHistory } from "@/components/research/SessionHistory";
import type { ResearchSession } from "@/lib/types";

export type AppView = "home" | "research" | "evaluation" | "memory" | "settings" | "about";

interface SidebarProps {
  active: AppView;
  /** True once a session is open, which reveals the Investigation entry. */
  hasSession: boolean;
  onNavigate: (view: AppView) => void;
  currentSessionId?: string;
  onSelectSession: (session: ResearchSession) => void;
  refreshTrigger: number;
  open: boolean;
  onClose: () => void;
}

export function Sidebar({
  active,
  hasSession,
  onNavigate,
  currentSessionId,
  onSelectSession,
  refreshTrigger,
  open,
  onClose,
}: SidebarProps) {
  return (
    <>
      {open && (
        <button
          type="button"
          className="sidebar-backdrop"
          onClick={onClose}
          aria-label="Close menu"
          tabIndex={-1}
        />
      )}
      <aside
        id="app-sidebar"
        className={`sidebar${open ? " sidebar-open" : ""}`}
        aria-label="Main menu"
      >
        <button
          type="button"
          className="sidebar-brand"
          onClick={() => onNavigate("home")}
        >
          <span className="brand-mark" aria-hidden="true">
            <Sparkles size={17} />
          </span>
          <span style={{ minWidth: 0 }}>
            <span
              style={{
                display: "block",
                fontSize: "0.95rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                letterSpacing: "-0.01em",
              }}
            >
              SCAR
            </span>
            <span
              style={{
                display: "block",
                fontSize: "0.68rem",
                color: "var(--text-muted)",
              }}
            >
              Self-Correcting Agent for Research
            </span>
          </span>
        </button>

        <nav className="sidebar-nav" aria-label="Sections">
          <button
            type="button"
            className="nav-item"
            aria-current={active === "home" ? "page" : undefined}
            onClick={() => onNavigate("home")}
          >
            <Sparkles size={15} aria-hidden="true" />
            New research
          </button>
          {hasSession && (
            <button
              type="button"
              className="nav-item"
              aria-current={active === "research" ? "page" : undefined}
              onClick={() => onNavigate("research")}
            >
              <Activity size={15} aria-hidden="true" />
              Investigation
            </button>
          )}
          <button
            type="button"
            className="nav-item"
            aria-current={active === "evaluation" ? "page" : undefined}
            onClick={() => onNavigate("evaluation")}
          >
            <Brain size={15} aria-hidden="true" />
            RL evaluation
          </button>
          <button
            type="button"
            className="nav-item"
            aria-current={active === "memory" ? "page" : undefined}
            onClick={() => onNavigate("memory")}
          >
            <Archive size={15} aria-hidden="true" />
            Long-term memory
          </button>
          <button
            type="button"
            className="nav-item"
            aria-current={active === "settings" ? "page" : undefined}
            onClick={() => onNavigate("settings")}
          >
            <Settings size={15} aria-hidden="true" />
            Settings
          </button>
          <button
            type="button"
            className="nav-item"
            aria-current={active === "about" ? "page" : undefined}
            onClick={() => onNavigate("about")}
          >
            <Info size={15} aria-hidden="true" />
            About
          </button>
        </nav>

        <div className="sidebar-section">
          <SessionHistory
            currentSessionId={currentSessionId}
            onSelectSession={onSelectSession}
            refreshTrigger={refreshTrigger}
          />
        </div>

        <div
          className="sidebar-footer"
          style={{
            marginTop: "auto",
            paddingTop: 12,
            borderTop: "1px solid var(--border)",
          }}
        >
          <button
            type="button"
            className="sidebar-close-btn"
            onClick={onClose}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              width: "100%",
              padding: "8px 10px",
              border: "none",
              background: "var(--bg-subtle)",
              borderRadius: 8,
              color: "var(--text-muted)",
              fontFamily: "inherit",
              fontSize: "0.78rem",
              fontWeight: 500,
              cursor: "pointer",
              transition: "background var(--duration-fast) var(--ease-standard), color var(--duration-fast) var(--ease-standard)",
            }}
          >
            <X size={14} aria-hidden="true" />
            Hide menu
          </button>
        </div>
      </aside>
    </>
  );
}

// Placeholder for future Tailwind class if decided.
// Currently used via inline style in Sidebar.
export {};