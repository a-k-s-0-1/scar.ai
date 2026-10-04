"use client";

// Facet coverage: the dimensions a research question decomposes into and how
// much evidence each one has. The server derives it once per iteration and
// streams it on the same channel as the rest of the run, so reading it back out
// of the message list works identically for a live run and a replay.

import type { FacetCoverageEntry, WSMessage } from "./types";

export interface FacetState {
  /** Mean coverage across the question's dimensions. */
  coverage: number;
  /** Dimensions still missing evidence, most valuable first. */
  gaps: string[];
  facets: FacetCoverageEntry[];
  iteration: number | null;
}

function isFacetEntry(value: unknown): value is FacetCoverageEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return typeof entry.facet === "string" && typeof entry.coverage === "number";
}

/**
 * Newest facet snapshot in a message list, or null when none was ever sent
 * (older runs predate facet planning).
 */
export function latestFacetState(messages: WSMessage[]): FacetState | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!Array.isArray(message.facets)) continue;

    const facets = message.facets.filter(isFacetEntry);
    if (facets.length === 0) continue;

    return {
      coverage:
        typeof message.facet_coverage === "number" ? message.facet_coverage : 0,
      gaps: Array.isArray(message.facet_gaps) ? message.facet_gaps : [],
      facets,
      iteration:
        typeof message.iteration === "number" ? message.iteration : null,
    };
  }
  return null;
}

/** "recent_evidence" → "Recent evidence" */
export function facetLabel(facet: string): string {
  const spaced = facet.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** Coverage colour band shared by the meter and its legend. */
export function facetTone(coverage: number): string {
  if (coverage < 0.5) return "var(--danger)";
  if (coverage < 0.8) return "var(--warn)";
  return "var(--ok)";
}
