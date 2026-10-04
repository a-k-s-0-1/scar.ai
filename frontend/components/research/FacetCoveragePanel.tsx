"use client";

import React from "react";
import { Compass } from "lucide-react";
import { facetLabel, facetTone, type FacetState } from "@/lib/facets";

/**
 * Which dimensions of the question the research has actually answered.
 *
 * Ordered weakest-first, because the point of the panel is the gap: a viability
 * answer with no cost evidence is incomplete however many technical claims were
 * collected.
 */
export function FacetCoveragePanel({ state }: { state: FacetState | null }) {
  if (!state || state.facets.length === 0) return null;

  const ordered = [...state.facets].sort(
    (a, b) => a.coverage - b.coverage || a.facet.localeCompare(b.facet)
  );
  const missing = state.gaps.map(facetLabel);
  const nextTarget = state.gaps[0] ? facetLabel(state.gaps[0]) : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: "0.72rem",
            fontWeight: 700,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            color: "var(--text-muted)",
          }}
        >
          <Compass size={13} aria-hidden="true" />
          Research coverage by dimension
        </span>
        <span
          className="mono-num"
          style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}
        >
          {Math.round(state.coverage * 100)}% overall
          {state.iteration !== null ? ` · iteration ${state.iteration}` : ""}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        {ordered.map((entry) => {
          const percent = Math.round(entry.coverage * 100);
          return (
            <div
              key={entry.facet}
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(96px, 148px) 1fr auto",
                gap: 10,
                alignItems: "center",
              }}
            >
              <span
                title={
                  entry.is_gap
                    ? `${facetLabel(entry.facet)}: no evidence yet — the next search targets it`
                    : `${facetLabel(entry.facet)}: ${entry.claims} claim(s)`
                }
                style={{
                  fontSize: "0.76rem",
                  fontWeight: entry.is_gap ? 700 : 500,
                  color: entry.is_gap
                    ? "var(--text-primary)"
                    : "var(--text-muted)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {facetLabel(entry.facet)}
              </span>

              <span
                role="progressbar"
                aria-label={`${facetLabel(entry.facet)} coverage`}
                aria-valuenow={percent}
                aria-valuemin={0}
                aria-valuemax={100}
                style={{
                  display: "block",
                  height: 6,
                  borderRadius: 3,
                  background: "var(--track)",
                  overflow: "hidden",
                }}
              >
                <span
                  style={{
                    display: "block",
                    height: "100%",
                    borderRadius: 3,
                    // A dimension with a single claim still shows a sliver, so the
                    // bar distinguishes "one claim" from "nothing at all".
                    width: `${
                      entry.claims > 0 ? Math.max(percent, 4) : 0
                    }%`,
                    background: facetTone(entry.coverage),
                    transition:
                      "width var(--duration-base) var(--ease-standard)",
                  }}
                />
              </span>

              <span
                className="mono-num"
                style={{
                  fontSize: "0.72rem",
                  color: "var(--text-muted)",
                  textAlign: "right",
                  whiteSpace: "nowrap",
                }}
              >
                {percent}% · {entry.claims}
              </span>
            </div>
          );
        })}
      </div>

      <p
        style={{
          fontSize: "0.74rem",
          lineHeight: 1.5,
          color: missing.length > 0 ? "var(--warn)" : "var(--text-muted)",
        }}
      >
        {missing.length > 0
          ? `Still missing evidence: ${missing.join(", ")}.${
              nextTarget ? ` Next search targets ${nextTarget}.` : ""
            }`
          : "Every dimension of the question has evidence behind it."}
      </p>
    </div>
  );
}
