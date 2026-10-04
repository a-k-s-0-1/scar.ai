"use client";

import React from "react";
import {
  AlertTriangle,
  Brain,
  Check,
  CircleCheck,
  CircleX,
  FileText,
  Network,
  RefreshCw,
  Scissors,
  Search,
  Square,
  Zap,
} from "lucide-react";
import type { ActivityItem, WSMessageType } from "../../lib/types";

// One icon + colour per stream event type, so the log scans by shape alone.
const TYPE_STYLES: Partial<
  Record<WSMessageType, { color: string; Icon: React.ComponentType<{ size?: number }> }>
> = {
  initialized: { color: "var(--accent)", Icon: Zap },
  search_started: { color: "var(--chart-2)", Icon: Search },
  sources_found: { color: "var(--chart-2)", Icon: FileText },
  extraction_started: { color: "var(--chart-3)", Icon: Scissors },
  claims_extracted: { color: "var(--ok)", Icon: Check },
  knowledge_updated: { color: "var(--accent)", Icon: Network },
  contradiction_detected: { color: "var(--warn)", Icon: AlertTriangle },
  decision_made: { color: "var(--accent-ink)", Icon: Brain },
  iteration_complete: { color: "var(--ok)", Icon: RefreshCw },
  completed: { color: "var(--ok)", Icon: CircleCheck },
  stopped: { color: "var(--warn)", Icon: Square },
  error: { color: "var(--danger)", Icon: CircleX },
};

interface ActivityFeedProps {
  items: ActivityItem[];
  className?: string;
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function ActivityFeed({ items, className = "" }: ActivityFeedProps) {
  return (
    <div className={className} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {items.length === 0 && (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            fontSize: "0.85rem",
            padding: "24px 0",
          }}
        >
          Activity will appear here once research begins…
        </div>
      )}
      {items.map((item) => {
        const style = TYPE_STYLES[item.type];
        const color = style?.color ?? "var(--chart-neutral)";
        const Icon = style?.Icon;
        return (
          <div
            key={item.id}
            className="animate-fade-in-up"
            style={{
              display: "flex",
              gap: 10,
              padding: "8px 10px",
              borderRadius: 8,
              background: "var(--bg-subtle)",
              borderLeft: `2px solid ${color}`,
              alignItems: "flex-start",
            }}
          >
            <span
              aria-hidden="true"
              style={{ color, flexShrink: 0, marginTop: 2, display: "flex" }}
            >
              {Icon ? <Icon size={14} /> : null}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p
                style={{
                  fontSize: "0.8rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.4,
                  wordBreak: "break-word",
                }}
              >
                {item.message}
              </p>
            </div>
            <span
              className="mono-num"
              style={{
                fontSize: "0.68rem",
                color: "var(--text-muted)",
                flexShrink: 0,
                marginTop: 2,
              }}
            >
              {formatTime(item.timestamp)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
