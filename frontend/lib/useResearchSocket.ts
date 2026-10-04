"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { createResearchSocket } from "./api";
import { facetLabel } from "./facets";
import type {
  WSMessage,
  ActivityItem,
  WSMessageType,
} from "./types";
export function humanizeMessage(msg: WSMessage): string {
  switch (msg.type) {
    case "initialized":
      return `Research session initialized for: "${msg.question}"`;
    case "memory_recalled":
      const recalledItems = Array.isArray(msg.items) ? msg.items : [];
      const recalledText =
        recalledItems.length > 0
          ? ` — ${recalledItems.length} prior ${recalledItems.length === 1 ? "memory item" : "memory items"} recalled`
          : "";
      return `Memory recalled from prior sessions${recalledText}`;
    case "memory_updated":
      const storedCounts = msg.stored && typeof msg.stored === "object" ? msg.stored : null;
      const storedText =
        storedCounts && Object.keys(storedCounts).length > 0
          ? ` — stored ${Object.values(storedCounts).reduce((a, b) => a + (Number(b) || 0), 0)} item(s)`
          : "";
      return `Long-term memory updated${storedText}`;
    case "search_started":
      return `[Iter ${msg.iteration}] Searching${
        msg.facet ? ` (${facetLabel(msg.facet)} angle)` : ""
      }: "${msg.query}"`;
    case "sources_found":
      return `[Iter ${msg.iteration}] Found ${msg.count} new sources (${msg.total_sources} total)`;
    case "extraction_started":
      return `[Iter ${msg.iteration}] Extracting claims from ${msg.sources_count} sources…`;
    case "claims_extracted":
      return `[Iter ${msg.iteration}] Extracted ${msg.count} claims (${msg.total_claims} total)`;
    case "knowledge_updated":
      return `Knowledge graph updated: ${msg.nodes} nodes, ${msg.edges} edges`;
    case "facet_updated":
      return `[Iter ${msg.iteration}] Facet coverage ${((msg.facet_coverage ?? 0) * 100).toFixed(0)}%${msg.facet_gaps && msg.facet_gaps.length > 0 ? ` — still missing: ${msg.facet_gaps.slice(0, 3).map(facetLabel).join(", ")}` : " — every dimension covered"}`;
    case "ikf_updated":
      return `[Iter ${msg.iteration}] Knowledge assessed: ${msg.evidence?.claims ?? 0} claim(s) scored (${msg.evidence?.high ?? 0} high, ${msg.evidence?.low ?? 0} low evidence)${(msg.versions?.versioned ?? 0) > 0 ? `, ${msg.versions?.versioned} fact(s) tracked over time` : ""}${(msg.temporal_versions_suppressed ?? 0) > 0 ? ` — ${msg.temporal_versions_suppressed} false contradiction(s) filtered` : ""}`;
    case "contradiction_detected":
      return `Contradiction detected: ${msg.count} conflicting claim pair(s) (severity: ${msg.severity})`;
    case "decision_made":
      return `JEV decision: ${msg.action?.toUpperCase()} — ${msg.reasoning} (coverage: ${((msg.coverage ?? 0) * 100).toFixed(0)}%)`;
    case "transition_recorded":
      const r = msg.reward != null ? (msg.reward >= 0 ? `+${msg.reward.toFixed(2)}` : msg.reward.toFixed(2)) : "?";
      return `[Iter ${msg.iteration}] Recorded transition: ${msg.action?.toUpperCase()} reward ${r} (state ${msg.state_bytes ?? 0}B, hash ${msg.state_hash ?? "?"})`;
    case "rl_shadow":
      const rlAction = (msg.rl_action || "").toUpperCase();
      const jevAction = (msg.jev_action || "").toUpperCase();
      const agree = msg.disagreement === false;
      const shadowText = msg.fallback
        ? "RL policy unavailable — using JEV reference"
        : `${rlAction} (support ${msg.support ?? 0}, est. ${msg.rl_expected_value != null ? msg.rl_expected_value.toFixed(2) : "?"})`;
      return `RL shadow: would recommend ${shadowText} vs JEV ${jevAction} — ${agree ? "aligned" : "disagreement"}`;
    case "iteration_complete":
      return `[Iter ${msg.iteration}] Complete — info gain: ${((msg.information_gain ?? 0) * 100).toFixed(0)}%, coverage: ${((msg.coverage ?? 0) * 100).toFixed(0)}%`;
    case "synthesis_regenerated":
      return `Report re-synthesized (attempt ${msg.retry_count ?? 1}) — ${msg.synthesis === "llm" ? "model summary" : "fallback summary retained"}`;
    case "completed":
      return `Research complete: ${msg.total_claims} claims from ${msg.total_sources} sources.`;
    case "stopped":
      return `Research stopped${msg.by ? ` by ${msg.by}` : ""}.`;
    case "error":
      return `Error: ${msg.message}`;
    default:
      return JSON.stringify(msg);
  }
}
export interface UseResearchSocketReturn {
  messages: WSMessage[];
  activity: ActivityItem[];
  isConnected: boolean;
  latestMessage: WSMessage | null;
  connect: (sessionId: string) => void;
  disconnect: () => void;
}
let activityIdCounter = 0;
export function toActivityItem(
  msg: WSMessage,
  timestamp: Date = new Date(),
  id?: string
): ActivityItem {
  return {
    id: id ?? String(++activityIdCounter),
    timestamp,
    type: msg.type as WSMessageType,
    message: humanizeMessage(msg),
    meta: msg as unknown as Record<string, unknown>,
    seq: typeof msg.seq === "number" ? msg.seq : undefined,
  };
}
export function useResearchSocket(): UseResearchSocketReturn {
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [latestMessage, setLatestMessage] = useState<WSMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);
  const connect = useCallback(
    (sessionId: string) => {
      disconnect();
      sessionIdRef.current = sessionId;
      const ws = createResearchSocket(sessionId);
      wsRef.current = ws;
      ws.onopen = () => {
        setIsConnected(true);
      };
      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg: WSMessage = JSON.parse(event.data as string);
          setLatestMessage(msg);
          setMessages((prev) => [...prev, msg]);
          setActivity((prev) => [toActivityItem(msg), ...prev].slice(0, 400));
        } catch {
          // non-JSON message, ignore
        }
      };
      ws.onerror = () => {
        setIsConnected(false);
      };
      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;
      };
    },
    [disconnect]
  );
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);
  return { messages, activity, isConnected, latestMessage, connect, disconnect };
}
