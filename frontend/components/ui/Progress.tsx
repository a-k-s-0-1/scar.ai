"use client";

import React from "react";

interface ProgressRingProps {
  value: number; // 0–1
  size?: number;
  strokeWidth?: number;
  label?: string;
  sublabel?: string;
  color?: string;
}

export function ProgressRing({
  value,
  size = 80,
  strokeWidth = 6,
  label,
  sublabel,
  color = "var(--accent)",
}: ProgressRingProps) {
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - Math.min(Math.max(value, 0), 1));

  return (
    <div
      className="flex flex-col items-center gap-1"
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div style={{ position: "relative", width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
          {/* Track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--track)"
            strokeWidth={strokeWidth}
          />
          {/* Progress */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            style={{ transition: "stroke-dashoffset 0.5s ease" }}
          />
        </svg>
        {label && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <span
              style={{
                fontSize: size < 64 ? "0.72rem" : "0.88rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                lineHeight: 1,
              }}
            >
              {label}
            </span>
          </div>
        )}
      </div>
      {sublabel && (
        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", textAlign: "center" }}>
          {sublabel}
        </span>
      )}
    </div>
  );
}

interface LinearProgressProps {
  value: number; // 0–1
  height?: number;
  animated?: boolean;
}

export function LinearProgress({
  value,
  height = 4,
  animated = true,
}: LinearProgressProps) {
  return (
    <div
      style={{
        width: "100%",
        height,
        background: "var(--track)",
        borderRadius: height,
        overflow: "hidden",
      }}
      role="progressbar"
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="progress-bar"
        style={{
          height: "100%",
          width: `${Math.min(Math.max(value * 100, 0), 100)}%`,
          transition: animated ? "width 0.5s ease" : "none",
        }}
      />
    </div>
  );
}
