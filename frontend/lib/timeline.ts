"use client";

// Session timelines: the activity log used to be fed only by the live WebSocket,
// so opening a finished investigation showed an empty panel. The server now keeps
// every broadcast, and this module turns that store back into feed rows, merges
// them with anything still arriving live, and reconstructs a minimal timeline for
// runs that predate the event log.

import { listSessionEvents } from "./api";
import { toActivityItem } from "./useResearchSocket";
import type {
  ActivityItem,
  ResearchReport,
  SessionEvent,
  WSMessage,
  MemoryItemModel,
} from "./types";

export interface SessionTimeline {
  /** Chronological (oldest first) messages. */
  messages: WSMessage[];
  /** Newest first, the order the activity feed renders. */
  activity: ActivityItem[];
  /** Sequence of the newest stored event; live messages after this are new. */
  latestSeq: number;
}

/** Page size for the event log; matches the API's maximum useful default. */
const PAGE_SIZE = 500;

function eventToMessage(event: SessionEvent): WSMessage {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  return {
    // The payload is the original broadcast; the columns add what an older row
    // may have been stored without.
    ...payload,
    type: (event.type as WSMessage["type"]) ?? (payload.type as WSMessage["type"]),
    seq: event.seq,
    iteration:
      typeof payload.iteration === "number"
        ? (payload.iteration as number)
        : event.iteration ?? undefined,
    // V2 offline-learning events carry the same fields as their WS broadcast.
    transition_id: payload.transition_id,
    reward: payload.reward,
    reward_components: payload.reward_components,
    state_hash: payload.state_hash,
    state_bytes: payload.state_bytes,
    sources_added: payload.sources_added,
    claims_added: payload.claims_added,
    information_gain: payload.information_gain,
    policy_id: payload.policy_id,
    policy_algorithm: payload.policy_algorithm,
    jev_action: payload.jev_action,
    jev_reasoning: payload.jev_reasoning,
    jev_expected_value: payload.jev_expected_value,
    rl_action: payload.rl_action,
    rl_expected_value: payload.rl_expected_value,
    rl_scores: payload.rl_scores,
    support: payload.support,
    fallback: payload.fallback,
    disagreement: payload.disagreement,
    prediction_id: payload.prediction_id,
    state_key: payload.state_key,
    items: (Array.isArray(payload.items) ? payload.items : null) as MemoryItemModel[] | null,
    stored: payload.stored,
    dead_ends_seeded: payload.dead_ends_seeded,
    entities_seeded: payload.entities_seeded,
  } as unknown as WSMessage;
}

function eventTimestamp(event: SessionEvent): Date {
  const parsed = new Date(event.created_at);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

/**
 * Load a session's persisted timeline, paging through the whole log.
 *
 * Returns messages in chronological order and the activity list newest-first,
 * with each row dated from the moment the event was actually stored.
 */
export async function loadSessionTimeline(sessionId: string): Promise<SessionTimeline> {
  const events: SessionEvent[] = [];
  let afterSeq = 0;
  let latestSeq = 0;

  for (;;) {
    const page = await listSessionEvents(sessionId, afterSeq, PAGE_SIZE);
    events.push(...page.events);
    latestSeq = page.latest_seq;
    if (page.events.length < PAGE_SIZE) break;
    afterSeq = page.latest_seq;
  }

  const messages = events.map(eventToMessage);
  const activity = events
    .map((event) =>
      toActivityItem(eventToMessage(event), eventTimestamp(event), `stored-${event.seq}`)
    )
    .reverse();

  return { messages, activity, latestSeq };
}

/** Live rows that are not already covered by the replayed history. */
export function mergeLiveActivity(
  replayed: ActivityItem[],
  live: ActivityItem[],
  replayedMaxSeq: number
): ActivityItem[] {
  const fresh = live.filter((item) => (item.seq ?? Number.MAX_SAFE_INTEGER) > replayedMaxSeq);
  return [...fresh, ...replayed];
}

/** Live messages that arrived after the replayed history ends. */
export function mergeLiveMessages(
  replayed: WSMessage[],
  live: WSMessage[],
  replayedMaxSeq: number
): WSMessage[] {
  const fresh = live.filter(
    (message) => (message.seq ?? Number.MAX_SAFE_INTEGER) > replayedMaxSeq
  );
  return [...replayed, ...fresh];
}

/**
 * Minimal timeline for sessions recorded before event persistence existed.
 *
 * Rebuilt from the saved report and labelled as such, so the feed never implies a
 * live log that was never captured.
 */
export function timelineFromReport(report: ResearchReport): SessionTimeline {
  const meta = report.metadata ?? {};
  const parsed = meta.generated_at ? new Date(meta.generated_at) : new Date();
  const when = Number.isNaN(parsed.getTime()) ? new Date() : parsed;

  const rows: { message: string; type: WSMessage["type"] }[] = [
    {
      message:
        "This run finished before event history was recorded, so this timeline is reconstructed from its saved report.",
      type: "initialized",
    },
  ];

  if (meta.total_sources) {
    rows.push({
      message: `Collected ${meta.total_sources} sources and extracted ${meta.total_claims ?? 0} claims.`,
      type: "claims_extracted",
    });
    rows.push({
      message: `Fused ${meta.total_nodes ?? 0} entities and ${
        meta.total_edges ?? 0
      } relationships into the knowledge graph.`,
      type: "knowledge_updated",
    });
  }
  if (typeof meta.coverage === "number") {
    rows.push({
      message: `Final coverage ${Math.round(meta.coverage * 100)}% after ${
        meta.iterations_completed ?? "several"
      } iteration(s).`,
      type: "decision_made",
    });
  }
  rows.push({ message: "Report compiled and stored.", type: "completed" });

  if (rows.length === 0) {
    rows.push({ message: "Run completed with no reconstructable events.", type: "completed" });
  }

  const activity: ActivityItem[] = rows
    .map((row, index) => ({
      id: `report-${index}`,
      timestamp: when,
      type: row.type,
      message: row.message,
    }))
    .reverse();

  return { messages: [], activity, latestSeq: 0 };
}
