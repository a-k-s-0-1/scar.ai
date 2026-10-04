"use client";

import React from "react";
import type { SessionStatus } from "../../lib/types";

// Status pill: colour + wording only, so it reads the same in both themes.
const statusTokens: Record<
  SessionStatus,
  { label: string; color: string; background: string }
> = {
  initializing: {
    label: "Initializing",
    color: "var(--text-muted)",
    background: "var(--bg-inset)",
  },
  pending: {
    label: "Pending",
    color: "var(--text-muted)",
    background: "var(--bg-inset)",
  },
  running: {
    label: "Running",
    color: "var(--info)",
    background: "var(--info-soft)",
  },
  completed: {
    label: "Completed",
    color: "var(--ok)",
    background: "var(--ok-soft)",
  },
  error: {
    label: "Error",
    color: "var(--danger)",
    background: "var(--danger-soft)",
  },
  stopped: {
    label: "Stopped",
    color: "var(--warn)",
    background: "var(--warn-soft)",
  },
};

interface StatusBadgeProps {
  status: SessionStatus;
  className?: string;
}

export function StatusBadge({ status, className = "" }: StatusBadgeProps) {
  const cfg = statusTokens[status] ?? statusTokens.pending;
  return (
    <span
      className={`badge ${className}`}
      style={{
        color: cfg.color,
        background: cfg.background,
        border: "1px solid currentColor",
      }}
    >
      <span
        aria-hidden="true"
        className={status === "running" ? "live-dot" : undefined}
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "currentColor",
          display: "inline-block",
          flexShrink: 0,
        }}
      />
      {cfg.label}
    </span>
  );
}
