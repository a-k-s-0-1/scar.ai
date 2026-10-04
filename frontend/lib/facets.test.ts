// Tests for the facet coverage view model.
//
// Run with `npm test`. Node executes the TypeScript directly, so the real module
// under test is the one the dashboard imports — no framework, no build step, and
// no duplicated expectations. This logic decides what the coverage panel shows, so
// the interesting cases are the ones the panel must not get wrong: which snapshot
// is newest, what a legacy run with no facet events looks like, and where the
// colour bands flip.

import assert from "node:assert/strict";
import { test } from "node:test";

import { facetLabel, facetTone, latestFacetState } from "./facets.ts";
import type { WSMessage } from "./types";

function snapshot(
  seq: number,
  iteration: number,
  coverage: number,
  facets: { facet: string; claims: number; coverage: number; is_gap: boolean }[],
  gaps: string[]
): WSMessage {
  return {
    type: "facet_updated",
    seq,
    iteration,
    facet_coverage: coverage,
    facet_gaps: gaps,
    facets,
  };
}

test("latestFacetState returns the newest snapshot, ignoring other messages", () => {
  const state = latestFacetState([
    { type: "initialized", seq: 1 },
    snapshot(2, 1, 0.25, [{ facet: "technical", claims: 1, coverage: 0.4, is_gap: true }], ["risks"]),
    { type: "search_started", seq: 3, query: "something" },
    snapshot(
      4,
      2,
      0.71,
      [
        { facet: "technical", claims: 8, coverage: 1, is_gap: false },
        { facet: "risks", claims: 0, coverage: 0, is_gap: true },
      ],
      ["risks", "alternatives"]
    ),
  ]);

  assert.ok(state);
  assert.equal(state.coverage, 0.71);
  assert.equal(state.iteration, 2);
  assert.deepEqual(state.gaps, ["risks", "alternatives"]);
  assert.equal(state.facets.length, 2);
  assert.equal(state.facets[1].facet, "risks");
});

test("latestFacetState is null for a run that never modelled facets", () => {
  // Runs recorded before facet planning must render no panel rather than an empty
  // shell claiming every dimension is uncovered.
  assert.equal(
    latestFacetState([
      { type: "initialized", seq: 1 },
      { type: "search_started", seq: 2, query: "q" },
      { type: "completed", seq: 3 },
    ]),
    null
  );
  assert.equal(latestFacetState([]), null);
});

test("latestFacetState ignores an empty or malformed facet list", () => {
  // Replayed payloads come out of the database as opaque JSON, so the panel must
  // survive a shape it did not write.
  assert.equal(
    latestFacetState([
      { type: "facet_updated", seq: 1, facet_coverage: 0.5, facets: [] },
      { type: "facet_updated", seq: 2, facet_coverage: 0.5, facets: "not-a-list" as unknown as WSMessage["facets"] },
      { type: "facet_updated", seq: 3, facets: [{ coverage: 1 } as never] },
    ]),
    null
  );
});

test("a snapshot without an iteration still reports its coverage", () => {
  const state = latestFacetState([
    snapshot(1, 1, 0.5, [{ facet: "technical", claims: 2, coverage: 0.5, is_gap: false }], []),
  ]);

  assert.ok(state);
  assert.equal(state.iteration, 1);
});

test("facetLabel turns a key into its display name", () => {
  assert.equal(facetLabel("recent_evidence"), "Recent evidence");
  assert.equal(facetLabel("risks"), "Risks");
  assert.equal(facetLabel("alternatives"), "Alternatives");
});

test("facetTone bands coverage the way the meter does", () => {
  assert.equal(facetTone(0), "var(--danger)");
  assert.equal(facetTone(0.49), "var(--danger)");
  assert.equal(facetTone(0.5), "var(--warn)");
  assert.equal(facetTone(0.79), "var(--warn)");
  assert.equal(facetTone(0.8), "var(--ok)");
  assert.equal(facetTone(1), "var(--ok)");
});
