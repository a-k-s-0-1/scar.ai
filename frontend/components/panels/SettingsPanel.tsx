"use client";

import React, { useCallback, useEffect, useState } from "react";
import { ExternalLink, Monitor, Moon, RefreshCw, Sun } from "lucide-react";
import { API_URL, getHealth } from "@/lib/api";
import { useDefaultDepth, useTheme, type ThemeMode } from "@/lib/preferences";
import type { DepthLevel } from "@/lib/types";

const THEME_OPTIONS: {
  value: ThemeMode;
  label: string;
  Icon: React.ComponentType<{ size?: number }>;
}[] = [
  { value: "system", label: "System", Icon: Monitor },
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
];

const DEPTH_OPTIONS: { value: DepthLevel; label: string; detail: string }[] = [
  { value: "shallow", label: "Quick", detail: "3 iterations · about 3 min" },
  {
    value: "standard",
    label: "Standard",
    detail: "5 iterations · about 5 min",
  },
  { value: "deep", label: "Deep", detail: "8 iterations · about 8 min" },
];

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ padding: "20px 22px" }}>
      <h3
        style={{
          fontSize: "0.95rem",
          fontWeight: 700,
          color: "var(--text-primary)",
          marginBottom: description ? 4 : 12,
        }}
      >
        {title}
      </h3>
      {description && (
        <p
          style={{
            fontSize: "0.82rem",
            color: "var(--text-secondary)",
            marginBottom: 12,
            lineHeight: 1.5,
          }}
        >
          {description}
        </p>
      )}
      {children}
    </div>
  );
}

type Health = "checking" | "ok" | "down";

export function SettingsPanel() {
  const { mode, resolved, setMode } = useTheme();
  const { depth, setDepth } = useDefaultDepth();
  const [health, setHealth] = useState<Health>("checking");
  const [environment, setEnvironment] = useState<string | null>(null);

  // Initial probe: state updates only after the await, so the effect never
  // re-enters and a failure is reported instead of assumed.
  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        const result = await getHealth();
        if (!ignore) {
          setHealth("ok");
          setEnvironment(result.environment);
        }
      } catch {
        if (!ignore) {
          setHealth("down");
          setEnvironment(null);
        }
      }
    })();
    return () => {
      ignore = true;
    };
  }, []);

  const checkHealth = useCallback(async () => {
    setHealth("checking");
    try {
      const result = await getHealth();
      setHealth("ok");
      setEnvironment(result.environment);
    } catch {
      setHealth("down");
      setEnvironment(null);
    }
  }, []);

  const healthColor =
    health === "ok"
      ? "var(--ok)"
      : health === "down"
        ? "var(--danger)"
        : "var(--text-muted)";
  const healthLabel =
    health === "ok"
      ? `Reachable${environment ? ` · ${environment}` : ""}`
      : health === "down"
        ? "Unreachable"
        : "Checking…";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Section
        title="Appearance"
        description="Light uses the pale orchid surfaces; dark switches to the deep purple workspace."
      >
        <div className="segmented" role="group" aria-label="Colour theme">
          {THEME_OPTIONS.map(({ value, label, Icon }) => (
            <button
              key={value}
              type="button"
              className="segmented-item"
              aria-pressed={mode === value}
              onClick={() => setMode(value)}
            >
              <Icon size={14} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
        <p
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            marginTop: 10,
          }}
        >
          {mode === "system"
            ? `Following your operating system — currently ${resolved}.`
            : `Always ${resolved}.`}
        </p>
      </Section>

      <Section
        title="Default research depth"
        description="Preselected on the new-research form. Greater depth means more iterations, more sources, and a longer run."
      >
        <div className="segmented" role="group" aria-label="Default research depth">
          {DEPTH_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className="segmented-item"
              aria-pressed={depth === value}
              onClick={() => setDepth(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <p
          style={{
            fontSize: "0.75rem",
            color: "var(--text-muted)",
            marginTop: 10,
          }}
        >
          {DEPTH_OPTIONS.find((option) => option.value === depth)?.detail}
        </p>
      </Section>

      <Section title="Connection">
        <dl
          style={{
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "8px 14px",
            fontSize: "0.82rem",
            alignItems: "center",
          }}
        >
          <dt style={{ color: "var(--text-muted)" }}>API base URL</dt>
          <dd
            className="mono-num"
            style={{ color: "var(--text-secondary)", wordBreak: "break-all" }}
          >
            {API_URL}
          </dd>
          <dt style={{ color: "var(--text-muted)" }}>Status</dt>
          <dd
            style={{
              color: healthColor,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              aria-hidden="true"
              className={health === "ok" ? "live-dot" : undefined}
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: "currentColor",
                display: "inline-block",
              }}
            />
            {healthLabel}
          </dd>
        </dl>
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 14,
            flexWrap: "wrap",
          }}
        >
          <button
            type="button"
            className="btn-secondary"
            onClick={checkHealth}
            disabled={health === "checking"}
            style={{ padding: "7px 14px", fontSize: "0.8rem" }}
          >
            <RefreshCw size={13} aria-hidden="true" />
            {health === "checking" ? "Checking…" : "Check again"}
          </button>
          <a
            className="btn-secondary"
            href={`${API_URL}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              padding: "7px 14px",
              fontSize: "0.8rem",
              textDecoration: "none",
            }}
          >
            <ExternalLink size={13} aria-hidden="true" />
            API documentation
          </a>
        </div>
      </Section>
    </div>
  );
}
