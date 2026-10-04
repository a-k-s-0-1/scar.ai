# LEARNINGS — Step-up pipeline session (2026-09-26)

Source: one continuous pass that ran 17 skill workflows in dependency order
(`code-review → brainstorm → debug-issue → python-testing → nodejs-patterns →
feature-development → optimize-codebase → overhaul → ui-ux-pro-max → enhance-ui →
experience → playtest → web-performance → gsd-audit-fix → gsd-autonomous →
gsd-extract-learnings → spec-brainstorm`) against the Self-Correcting Research Agent MVP.

Project had no git repository and no `.planning/` or `~/.claude/gsd-core/` artifacts,
so the three GSD workflows were executed from their intent using this session's own
findings as the phase record.

## Decisions

- **Convergence fix over cosmetic telemetry.** Root cause was three coupled defects
  (gain normalizers 6x below real yield, coverage capped at 1.0, and the gap-expansion
  branch shadowing the convergence STOP). Chose a *trend* rule (two consecutive
  low-novelty iterations, with one gap-directed attempt in between) instead of a single
  low-gain sample, so the corrective action still gets a chance to break the plateau.
- **Coverage became asymptotic, not ratio-capped.** `1 - exp(-1.6 * weighted_ratio)`,
  calibrated so meeting every depth target reads ~0.80 (the PRD's canonical stop
  threshold). A capped ratio is blind exactly when sessions are richest.
- **One depth profile module** (`app/services/depth_config.py`) replaced four copies of
  depth semantics (orchestrator caps, metric targets, API duration estimate, frontend
  iteration map).
- **Deep research was 100% broken and nobody noticed.** The form sent
  `max_research_time_minutes: 20` while the schema allows `le=10` → HTTP 422 for every
  deep run. Fixed on the client (5/8/10 minutes) rather than loosening the API guardrail.
- **Auth: enforce, don't pretend.** WebSockets now require the key as a query parameter
  (browsers cannot send headers) and the REST dev bypass is gated on
  `ENVIRONMENT == "development"`, so a non-dev deployment cannot silently serve
  unauthenticated requests.
- **Refactor, don't rewrite.** `ResearchDashboard.tsx` was split by moving JSX verbatim
  into `ReportView.tsx` and `DashboardStats.tsx`; the typecheck and eslint stayed clean
  and no logic changed.

## Lessons

- **Saturating metrics look like working dashboards.** Coverage and information gain had
  read `1.000` in every persisted decision record for months of runtime, yet the engine
  was advertising "self-correcting". A metric that can only report "full" is worse than
  no metric: it silently disables the rules that read it.
- **Persisted state is instrumentation you already own.** The `decisions` table held
  `knowledge_state_snapshot` per iteration; replaying it through the pure functions was a
  complete MRE with zero new code.
- **Fallbacks need provenance.** Under provider rate limits the report fell back to
  "Research synthesis concluded with empirical evidence collected." — presented exactly
  like a synthesized summary. `metadata.synthesis` + a UI badge cost ~15 lines.
- **Absent data must not render as zero.** A completed session opened from history showed
  `0% coverage` and `KG Nodes 0` next to a report claiming 118 entities, because the
  dashboard only read the live WebSocket stream.
- **`overflow-x: hidden` turns a layout bug into a functional one.** At 390px the
  two-column home grid overflowed by 312px while the body clipped it, making the session
  history literally unreachable. Media queries in CSS (inline styles cannot express them)
  fixed it: overflow went −5px.
- **Free-tier keys are a shared resource.** Two concurrent sessions produced a 429 storm
  in both Gemini and Groq, crawling one session to 2 iterations in 15 minutes. A shared
  concurrency gate plus exponential backoff is the minimum viable mitigation.

## Patterns

- **Iron Law debugging**: reproduce from stored snapshots → isolate the three independent
  causes → one cohesive fix → replay the same snapshots to prove the new behavior
  (`gain` 1.0/0.524/0.158 instead of 1.0/1.0/1.0).
- **Isolated pytest fixtures for real behavior**: `state_factory` builds `KnowledgeState`
  from defaults, so decision-rule tables read as data, not setup. The launch-path test
  monkeypatches `ResearchOrchestrator` with a stub so no test touches the real database.
- **Reduced-motion + focus + mono numerals as tokens**: `--font-mono`, `--duration-fast`,
  `prefers-reduced-motion` blanket rule, `.mono-num` for live metrics.
- **Middleware trio for FastAPI** (the Node playbook's transferable part): correlation-ID
  middleware feeding the *same* id into error envelopes, a real `/health/ready` DB probe,
  and tracked background tasks with a duplicate-launch guard.

## Surprises

- Reconciling stale sessions on startup was not on any list — it was discovered by
  restarting the server during a live run and noticing a phantom "running" session.
  The fix verified itself on the next restart (`Reconciled 1 session(s)`).
- The evidence table was truncated to 15 of 90 claims *client-side*, so the API had always
  been correct; the lie was purely in the view.
- `next.config.ts` was empty and `vis-data` was installed but imported nowhere — the
  perf pass found the lazy `vis-network` chunk (648KB raw / 152KB gz) correctly excluded
  from first load (184KB gz, LCP 525ms, CLS 0.02 in production).
- The pre-existing eslint warning disappeared as a side effect of restructuring the
  session-history fetch (state updates moved after `await`).

## Open items

- Contradiction *negative* results are still not persisted, so non-contradicting pairs are
  re-evaluated on later iterations (positive pairs are now skipped).
- `frontend/lib/types.ts` remains hand-written; deriving it from the Pydantic schemas
  (openapi-typescript) is a deliberate codegen decision.
- Emoji are still used as icons in several places (the ui-ux-pro-max checklist calls this
  out); migrating to SVG icons needs an icon dependency.
- Docs sync (`memory.md` status block, `IMPLEMENTATION.md` phase checkboxes) was left
  untouched pending the user's preferred convention.
