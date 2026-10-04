"use client";

import React from "react";
import { X } from "lucide-react";

// Clickable metric cards plus the shared explanation panel they open. The panel
// sits directly beneath the stats grid, so a click on any card answers "what
// does this number actually mean?" without covering the data.

export interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  color: string;
  /** True when this card's explanation is the one on screen. */
  active: boolean;
  /** id of the ExplainPanel this card controls. */
  panelId: string;
  onToggle: () => void;
  children?: React.ReactNode;
}

export function MetricCard({
  label,
  value,
  icon,
  color,
  active,
  panelId,
  onToggle,
  children,
}: MetricCardProps) {
  return (
    <button
      type="button"
      className="card stat-card"
      aria-expanded={active}
      aria-controls={panelId}
      onClick={onToggle}
      title={`What is "${label}"?`}
    >
      <span
        aria-hidden="true"
        style={{ color, display: "flex", marginBottom: 6 }}
      >
        {icon}
      </span>
      {value !== undefined && value !== null && (
        <span
          className="mono-num"
          style={{
            fontSize: "1.5rem",
            fontWeight: 800,
            color,
            lineHeight: 1.1,
          }}
        >
          {value}
        </span>
      )}
      <span
        style={{
          fontSize: "0.72rem",
          color: "var(--text-muted)",
          fontWeight: 600,
        }}
      >
        {label}
      </span>
      {children}
      <span
        style={{
          fontSize: "0.65rem",
          color: active ? "var(--accent-ink)" : "var(--text-muted)",
          opacity: active ? 1 : 0.75,
        }}
      >
        {active ? "Hide definition" : "Tap for definition"}
      </span>
    </button>
  );
}

export interface ExplainerPanelProps {
  id: string;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}

export function ExplainerPanel({
  id,
  title,
  children,
  onClose,
}: ExplainerPanelProps) {
  return (
    <div
      id={id}
      role="region"
      aria-label={`${title} explained`}
      className="info-panel"
      style={{
        marginTop: 12,
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
      }}
    >
      <div style={{ flex: 1 }}>
        <span className="info-panel-title">{title}</span>
        {children}
      </div>
      <button
        type="button"
        className="icon-button"
        onClick={onClose}
        aria-label="Close definition"
        style={{ flexShrink: 0 }}
      >
        <X size={15} aria-hidden="true" />
      </button>
    </div>
  );
}
