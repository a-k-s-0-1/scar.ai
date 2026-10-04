"use client";

import React from "react";

// Shimmer placeholders used while data is in flight. The sweep animation is
// disabled by the global prefers-reduced-motion rule.

export function Skeleton({
  width = "100%",
  height = 12,
  radius = 6,
  style,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className="skeleton"
      aria-hidden="true"
      style={{
        display: "block",
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
    />
  );
}

/** Placeholder rows for lists that are still loading. */
export function SkeletonList({
  rows = 4,
  lines = 2,
  gap = 10,
  height = 52,
}: {
  rows?: number;
  lines?: number;
  gap?: number;
  height?: number;
}) {
  return (
    <div
      aria-hidden="true"
      style={{ display: "flex", flexDirection: "column", gap }}
    >
      {Array.from({ length: rows }).map((_, row) => (
        <div
          key={row}
          style={{
            height,
            padding: "10px 12px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--bg-subtle)",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            gap: 8,
          }}
        >
          {Array.from({ length: lines }).map((_, line) => (
            <Skeleton
              key={line}
              height={line === 0 ? 10 : 8}
              width={line === 0 ? "82%" : "46%"}
            />
          ))}
        </div>
      ))}
    </div>
  );
}
