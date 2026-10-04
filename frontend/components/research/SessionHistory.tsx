"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, Trash2 } from "lucide-react";
import { listSessions, deleteSession, getSession } from "@/lib/api";
import { SkeletonList } from "@/components/ui/Skeleton";
import type { SessionSummary, ResearchSession, SessionStatus } from "@/lib/types";

interface SessionHistoryProps {
  currentSessionId?: string;
  onSelectSession: (session: ResearchSession) => void;
  refreshTrigger?: number;
}

const STATUS_COLORS: Record<SessionStatus, string> = {
  initializing: "var(--text-muted)",
  pending: "var(--text-muted)",
  running: "var(--info)",
  completed: "var(--ok)",
  stopped: "var(--warn)",
  error: "var(--danger)",
};

function statusColor(status: string): string {
  return STATUS_COLORS[status as SessionStatus] ?? "var(--text-muted)";
}

export function SessionHistory({
  currentSessionId,
  onSelectSession,
  refreshTrigger = 0,
}: SessionHistoryProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // State updates happen only after the await, so the fetch never re-enters the
  // effect, and a backend outage surfaces as an error instead of a false
  // "no past sessions" empty state.
  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const items = await listSessions();
        if (!ignore) {
          setSessions(items);
          setError(null);
        }
      } catch {
        if (!ignore) {
          setError(
            "Could not load past investigations — the backend may be offline."
          );
        }
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => {
      ignore = true;
    };
  }, [refreshTrigger, refreshKey]);

  const refresh = () => {
    setLoading(true);
    setError(null);
    setRefreshKey((key) => key + 1);
  };

  const handleSelect = async (id: string) => {
    try {
      const session = await getSession(id);
      onSelectSession(session);
    } catch {
      setError("Could not open that investigation — it may have been deleted.");
    }
  };

  const handleDelete = async (id: string) => {
    if (deletingId) return;
    setDeletingId(id);
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
    } catch {
      setError("Could not delete that investigation. Try again.");
    } finally {
      setDeletingId(null);
    }
  };

  const showSkeletons = loading && sessions.length === 0;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        flex: 1,
        minHeight: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span className="sidebar-label">Past Investigations</span>
        <button
          onClick={refresh}
          disabled={loading}
          className="icon-button"
          aria-label="Refresh past investigations"
          title="Refresh"
        >
          <RefreshCw size={14} aria-hidden="true" />
        </button>
      </div>

      {error && (
        <div
          style={{
            fontSize: "0.78rem",
            color: "var(--danger)",
            padding: "12px",
            background: "var(--danger-soft)",
            border: "1px solid var(--danger-border)",
            borderRadius: 8,
            display: "flex",
            flexDirection: "column",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <span style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
            <AlertTriangle size={14} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
            <span>{error}</span>
          </span>
          <button
            onClick={refresh}
            className="btn-secondary"
            style={{ padding: "5px 12px", fontSize: "0.75rem" }}
          >
            <RefreshCw size={12} aria-hidden="true" />
            Retry
          </button>
        </div>
      )}

      {showSkeletons && <SkeletonList rows={4} height={58} />}

      {!loading && !error && sessions.length === 0 && (
        <div
          style={{
            fontSize: "0.8rem",
            color: "var(--text-muted)",
            padding: "16px 12px",
            textAlign: "center",
            background: "var(--bg-subtle)",
            borderRadius: 8,
            border: "1px dashed var(--border)",
          }}
        >
          No past sessions yet. Run an investigation to get started.
        </div>
      )}

      {!showSkeletons && sessions.length > 0 && (
        <div
          className="scroll-panel"
          style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1 }}
        >
          {sessions.map((s) => {
            const isSelected = s.id === currentSessionId;
            const color = statusColor(s.status);
            return (
              <div
                key={s.id}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 6,
                  padding: "9px 8px 9px 11px",
                  borderRadius: 10,
                  background: isSelected ? "var(--accent-soft)" : "var(--bg-subtle)",
                  border: isSelected
                    ? "1px solid var(--accent-border)"
                    : "1px solid var(--border)",
                  transition: "border-color 150ms ease, background 150ms ease",
                }}
              >
                <button
                  type="button"
                  onClick={() => handleSelect(s.id)}
                  aria-current={isSelected ? "true" : undefined}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    textAlign: "left",
                    background: "none",
                    border: "none",
                    padding: 0,
                    cursor: "pointer",
                    font: "inherit",
                    color: "inherit",
                  }}
                >
                  <span
                    style={{
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      fontSize: "0.8rem",
                      fontWeight: 600,
                      color: isSelected ? "var(--accent-ink)" : "var(--text-primary)",
                      lineHeight: 1.4,
                      marginBottom: 6,
                    }}
                  >
                    {s.question}
                  </span>

                  <span
                    style={{
                      display: "flex",
                      gap: 6,
                      alignItems: "center",
                      fontSize: "0.68rem",
                      color: "var(--text-muted)",
                    }}
                  >
                    <span
                      aria-hidden="true"
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        background: color,
                        display: "inline-block",
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ color, textTransform: "capitalize" }}>
                      {s.status}
                    </span>
                    <span aria-hidden="true">·</span>
                    <span className="mono-num">{s.sources_count} sources</span>
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => handleDelete(s.id)}
                  disabled={deletingId === s.id}
                  className="icon-button"
                  aria-label={`Delete investigation: ${s.question}`}
                  title="Delete investigation"
                  style={{ width: 26, height: 26 }}
                >
                  <Trash2 size={13} aria-hidden="true" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
