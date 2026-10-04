"use client";

import React, { useEffect, useState } from "react";
import { Archive, Search, GitBranch, Clock, Tag, Trash2, Loader2 } from "lucide-react";
import {
  listMemory,
  searchMemory,
  getMemoryConflicts,
  getMemoryForSession,
  promoteMemory,
  forgetMemoryItem,
} from "@/lib/api";
import type {
  MemoryItemModel,
  MemoryConflictItem,
  MemorySessionResponse,
} from "@/lib/types";

interface MemoryPanelProps {
  sessionId?: string;
  className?: string;
}

type View = "list" | "search" | "conflicts" | "session" | "session-promote";

function timeAgo(date: string | null | undefined): string {
  if (!date) return "unknown";
  const parsed = new Date(date);
  if (Number.isNaN(parsed.getTime())) return "invalid date";
  const diff = Date.now() - parsed.getTime();
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor(diff / 3600000);
  if (days > 30) return `${Math.floor(days / 30)}mo ago`;
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  return "just now";
}

function statusBadge(status: string): string {
  switch (status) {
    case "active":
      return "badge badge-green";
    case "superseded":
      return "badge badge-gray";
    case "conflicting":
      return "badge badge-warn";
    case "needs_verification":
      return "badge badge-amber";
    default:
      return "badge badge-gray";
  }
}

function importanceDot(value: number): string {
  if (value >= 0.8) return "dot-dot dot-ok";
  if (value >= 0.5) return "dot-dot dot-gray";
  return "dot-dot dot-warn";
}

export function MemoryPanel({ sessionId, className = "" }: MemoryPanelProps) {
  const [view, setView] = useState<View>("list");
  const [items, setItems] = useState<MemoryItemModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<MemoryItemModel[]>([]);
  const [conflicts, setConflicts] = useState<MemoryConflictItem[]>([]);
  const [conflictsLoading, setConflictsLoading] = useState(true);
  const [conflictDetail, setConflictDetail] = useState<string | null>(null);
  const [sessionItems, setSessionItems] = useState<MemorySessionResponse | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [promoteLoading, setPromoteLoading] = useState(false);
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const [promoteSuccess, setPromoteSuccess] = useState<string | null>(null);
  const [promoteMaxClaims, setPromoteMaxClaims] = useState(25);
  const [promoteMaxSources, setPromoteMaxSources] = useState(10);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await listMemory();
        if (!ignore) setItems(res.items);
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : "Could not load memory.");
      } finally {
        if (!ignore) setLoading(false);
      }
    })();
    return () => { ignore = true; };
  }, []);

  useEffect(() => {
    let ignore = false;
    (async () => {
      try {
        setConflictsLoading(true);
        const res = await getMemoryConflicts();
        if (!ignore) setConflicts(res.items);
      } catch {
        if (!ignore) setError("Could not load conflicts.");
      } finally {
        if (!ignore) setConflictsLoading(false);
      }
    })();
    return () => { ignore = true; };
  }, []);

  useEffect(() => {
    let ignore = false;
    if (sessionId && (view === "session" || view === "session-promote")) {
      (async () => {
        try {
          setSessionLoading(true);
          const res = await getMemoryForSession(sessionId);
          if (!ignore) setSessionItems(res);
        } catch {
          if (!ignore) setError("Could not load session memory.");
        } finally {
          if (!ignore) setSessionLoading(false);
        }
      })();
    }
    return () => { ignore = true; };
  }, [sessionId, view]);

  const runSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const res = await searchMemory(searchQuery.trim());
      setSearchResults(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setSearchLoading(false);
    }
  };

  const runPromote = async () => {
    if (!sessionId) return;
    setPromoteError(null);
    setPromoteSuccess(null);
    setPromoteLoading(true);
    try {
      const res = await promoteMemory(sessionId, promoteMaxClaims, promoteMaxSources);
      setPromoteSuccess(`Stored ${res.stored.source ?? res.stored.claim ?? 0} item(s); ${res.updates.conflicting ?? 0} conflict(s) updated.`);
      setSessionLoading(true);
    } catch (err) {
      setPromoteError(err instanceof Error ? err.message : "Promotion failed.");
    } finally {
      setPromoteLoading(false);
    }
  };

  const forget = async (id: string) => {
    if (!confirm("Forget this memory item?")) return;
    try {
      await forgetMemoryItem(id);
      setItems((prev) => prev.filter((it) => it.id !== id));
      setConflicts((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Forget failed.");
    }
  };

  const emptyMessage = (fallback: string) => {
    if (view === "search") return "Enter a query above and search.";
    return fallback;
  };

  return (
    <div className={`card ${className}`} style={{ padding: "18px 20px", maxWidth: 980 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <Archive size={18} style={{ color: "var(--chart-3)" }} aria-hidden="true" />
        <span style={{ fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
          Long-term memory
        </span>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
        {(["list", "search", "conflicts", "session"].filter((v) => v !== "session" || !!sessionId) as View[]).map((v) => (
          <button
            key={v}
            type="button"
            className={`btn-secondary${view === v ? " btn-active" : ""}`}
            onClick={() => setView(v)}
            style={{ padding: "6px 12px", fontSize: "0.8rem" }}
          >
            {v === "list" && <Archive size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {v === "search" && <Search size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {v === "conflicts" && <GitBranch size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {v === "session" && <Clock size={13} style={{ marginRight: 6 }} aria-hidden="true" />}
            {v === "list" && "All items"}
            {v === "search" && "Search"}
            {v === "conflicts" && "Conflicts"}
            {v === "session" && sessionId ? "Session" : "Session"}
          </button>
        ))}
      </div>

      {error && <div style={{ padding: "8px 12px", background: "var(--danger-soft)", borderRadius: 6, color: "var(--danger)", fontSize: "0.82rem", marginBottom: 12 }}>{error}</div>}
      {promoteSuccess && <div style={{ padding: "8px 12px", background: "var(--ok-soft)", borderRadius: 6, color: "var(--ok)", fontSize: "0.82rem", marginBottom: 12 }}>{promoteSuccess}</div>}
      {promoteError && <div style={{ padding: "8px 12px", background: "var(--danger-soft)", borderRadius: 6, color: "var(--danger)", fontSize: "0.82rem", marginBottom: 12 }}>{promoteError}</div>}

      {view === "list" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {loading ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", display: "flex", justifyContent: "center" }}>
              <Loader2 size={18} className="spin" aria-hidden="true" />
            </div>
          ) : items.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>{emptyMessage("No memory items stored yet.")}</div>
          ) : (
            items.map((item) => (
              <div key={item.id} style={{ padding: "10px 12px", background: "var(--bg-subtle)", borderRadius: 8, borderLeft: "2px solid var(--chart-3)" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "capitalize", color: "var(--text-primary)" }}>{item.kind}</span>
                      <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.7rem", color: "var(--text-muted)" }}>{item.key}</span>
                      <span className={importanceDot(item.importance)} style={{ flexShrink: 0 }} title={`importance ${item.importance.toFixed(2)}`} />
                      {item.source_session_id && (
                        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" }}>
                          sess {item.source_session_id.slice(0, 8)}
                        </span>
                      )}
                    </div>
                    <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.45, wordBreak: "break-word" }}>
                      {item.text}
                    </p>
                    {Object.keys(item.payload).length > 0 && (
                      <details style={{ marginTop: 6 }}>
                        <summary style={{ cursor: "pointer", fontSize: "0.7rem", color: "var(--text-muted)" }}>payload</summary>
                        <pre style={{ marginTop: 4, padding: "6px 8px", background: "var(--bg-hover)", borderRadius: 4, fontSize: "0.7rem", fontFamily: "ui-monospace, monospace", color: "var(--text-secondary)", overflow: "auto", maxHeight: 160 }}>
                          {JSON.stringify(item.payload, null, 2)}
                        </pre>
                      </details>
                    )}
                    <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: "0.7rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
                      <span>confidence {item.confidence.toFixed(2)}</span>
                      <span>hits {item.hits}</span>
                      {item.created_at && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Clock size={10} aria-hidden="true" />{timeAgo(item.created_at)}</span>}
                      {item.source_session_id && (
                        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <Tag size={10} aria-hidden="true" />from session {item.source_session_id.slice(0, 8)}
                        </span>
                      )}
                    </div>
                  </div>
                  <button type="button" className="btn-secondary" style={{ padding: "3px 8px", fontSize: "0.72rem" }} onClick={() => forget(item.id)}>
                    <Trash2 size={12} aria-hidden="true" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {view === "search" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="Search prior knowledge…"
              style={{ flex: 1, padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg-subtle)", color: "var(--text-primary)", fontSize: "0.85rem" }}
            />
            <button type="button" className="btn-glow" onClick={runSearch} disabled={searchLoading || !searchQuery.trim()} style={{ padding: "8px 16px", fontSize: "0.82rem", display: "flex", alignItems: "center", gap: 6 }}>
              {searchLoading ? <Loader2 size={14} className="spin" aria-hidden="true" /> : <Search size={14} aria-hidden="true" />}
              {searchLoading ? "Searching…" : "Search"}
            </button>
          </div>
          {searchResults.length > 0 ? (
            searchResults.map((item) => <MemoryItemKey key={item.id} item={item} />)
          ) : searchQuery.trim() === "" ? null : (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
              {searchLoading ? "Searching…" : "No matches."}
            </div>
          )}
        </div>
      )}

      {view === "conflicts" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {conflictsLoading ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", display: "flex", justifyContent: "center" }}>
              <Loader2 size={18} className="spin" aria-hidden="true" />
            </div>
          ) : conflicts.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>No versioned or conflicting memories.</div>
          ) : (
            conflicts.map((item) => (
              <div key={item.id} style={{ padding: "12px 14px", background: "var(--bg-subtle)", borderRadius: 8, borderLeft: `2px solid ${item.status === "conflicting" ? "var(--warn)" : item.status === "superseded" ? "var(--chart-2)" : "var(--chart-3)"}` }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "var(--text-primary)" }}>{item.key}</span>
                      <span className={statusBadge(item.status)}>{item.status}</span>
                      {item.subject && <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" }}>{item.subject} → {item.predicate}</span>}
                      <span style={{ marginLeft: "auto", fontSize: "0.72rem", color: "var(--text-muted)" }}>{item.conflicts} conflict(s)</span>
                    </div>
                    <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.45, wordBreak: "break-word" }}>{item.text}</p>
                    <div style={{ display: "flex", gap: 10, marginTop: 6, fontSize: "0.7rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
                      <span>confirmations {item.confirmation_count}</span>
                      <span>importance {item.importance.toFixed(2)}</span>
                      <span>confidence {item.confidence.toFixed(2)}</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Tag size={10} aria-hidden="true" />{item.sources.length} source(s)</span>
                      {item.provenance.session_id && (
                        <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Clock size={10} aria-hidden="true" />from session {item.provenance.session_id.slice(0, 8)}</span>
                      )}
                    </div>
                    {conflictDetail === item.id && item.versions && item.versions.length > 0 && (
                      <div style={{ marginTop: 10, padding: "8px 10px", background: "var(--bg-hover)", borderRadius: 6 }}>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.04em" }}>Versions ({item.versions.length})</div>
                        {item.versions.map((v) => (
                          <div key={v.recorded_at ?? v.value} style={{ padding: "6px 8px", background: "var(--bg-subtle)", borderRadius: 4, marginBottom: 4 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                              <span className={statusBadge(v.status)} style={{ fontSize: "0.65rem" }}>{v.status}</span>
                              <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" }}>
                                {v.valid_from != null ? `from ${v.valid_from}` : ""}
                                {v.valid_to != null ? ` → ${v.valid_to}` : ""}
                              </span>
                            </div>
                            <p style={{ margin: 0, fontSize: "0.78rem", color: "var(--text-secondary)" }}>{v.text}</p>
                            <div style={{ display: "flex", gap: 8, marginTop: 4, fontSize: "0.68rem", color: "var(--text-muted)" }}>
                              {v.session_id && <span>session {v.session_id.slice(0, 8)}</span>}
                              <span style={{ fontFamily: "ui-monospace, monospace" }}>confidence {v.confidence.toFixed(2)}</span>
                              {v.recorded_at && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Clock size={9} aria-hidden="true" />{timeAgo(v.recorded_at)}</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    {!conflictDetail && item.versions && item.versions.length > 1 && (
                      <button type="button" className="btn-secondary" style={{ marginTop: 8, padding: "3px 8px", fontSize: "0.72rem" }} onClick={() => setConflictDetail(conflictDetail === item.id ? null : item.id)}>
                        <GitBranch size={11} style={{ marginRight: 4 }} aria-hidden="true" />
                        {conflictDetail === item.id ? "Hide versions" : `${item.versions.length} versions`}
                      </button>
                    )}
                  </div>
                  <button type="button" className="btn-secondary" style={{ padding: "3px 8px", fontSize: "0.72rem" }} onClick={() => forget(item.id)}>
                    <Trash2 size={12} aria-hidden="true" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {view === "session" && sessionId && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {sessionLoading ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", display: "flex", justifyContent: "center" }}>
              <Loader2 size={18} className="spin" aria-hidden="true" />
            </div>
          ) : sessionItems && sessionItems.items.length > 0 ? (
            <>
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Session <span style={{ fontFamily: "ui-monospace, monospace" }}>{sessionId.slice(0, 8)}</span> contributed{" "}
                {sessionItems.items.length} item(s) to long-term memory.
              </div>
              {sessionItems.items.map((item) => <MemoryItemKey key={item.id} item={item} showSession />)}
              <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", padding: "10px 12px", background: "var(--bg-subtle)", borderRadius: 8 }}>
                <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Re-promote this session:</span>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>claims</label>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={promoteMaxClaims}
                    onChange={(e) => setPromoteMaxClaims(Number(e.target.value))}
                    style={{ width: 60, padding: "3px 6px", border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-hover)", color: "var(--text-primary)", fontSize: "0.8rem" }}
                  />
                  <label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>sources</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={promoteMaxSources}
                    onChange={(e) => setPromoteMaxSources(Number(e.target.value))}
                    style={{ width: 60, padding: "3px 6px", border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg-hover)", color: "var(--text-primary)", fontSize: "0.8rem" }}
                  />
                </div>
                <button
                  type="button"
                  className="btn-glow"
                  onClick={runPromote}
                  disabled={promoteLoading}
                  style={{ marginLeft: "auto", padding: "6px 12px", fontSize: "0.78rem", display: "flex", alignItems: "center", gap: 6 }}
                >
                  {promoteLoading ? <Loader2 size={13} className="spin" aria-hidden="true" /> : <Archive size={13} aria-hidden="true" />}
                  {promoteLoading ? "Promoting…" : "Promote"}
                </button>
              </div>
            </>
          ) : sessionItems && sessionItems.items.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
              This session has not contributed any durable memory yet.
            </div>
          ) : null}
        </div>
      )}

      {view === "session-promote" && sessionId && (
        <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
          Switch to the Session view to see this session&apos;s contributions.
        </div>
      )}
    </div>
  );
}

function MemoryItemKey({ item, showSession }: { item: MemoryItemModel; showSession?: boolean }) {
  return (
    <div style={{ padding: "10px 12px", background: "var(--bg-subtle)", borderRadius: 8, borderLeft: "2px solid var(--chart-3)" }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontWeight: 700, fontSize: "0.85rem", textTransform: "capitalize", color: "var(--text-primary)" }}>{item.kind}</span>
            <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.7rem", color: "var(--text-muted)" }}>{item.key}</span>
            {item.source_session_id && (
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "ui-monospace, monospace" }}>
                sess {item.source_session_id.slice(0, 8)}
              </span>
            )}
            {showSession && item.source_session_id && (
              <span style={{ fontSize: "0.7rem", color: "var(--accent)", fontFamily: "ui-monospace, monospace" }}>
                ← you
              </span>
            )}
          </div>
          <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-secondary)", lineHeight: 1.45, wordBreak: "break-word" }}>{item.text}</p>
          <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: "0.7rem", color: "var(--text-muted)", flexWrap: "wrap" }}>
            <span>confidence {item.confidence.toFixed(2)}</span>
            <span>importance {item.importance.toFixed(2)}</span>
            <span>hits {item.hits}</span>
            {item.created_at && <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Clock size={10} aria-hidden="true" />{timeAgo(item.created_at)}</span>}
            {showSession && item.source_session_id && (
              <span style={{ display: "flex", alignItems: "center", gap: 4 }}><Tag size={10} aria-hidden="true" />from session {item.source_session_id.slice(0, 8)}</span>
            )}
          </div>
        </div>
        <button type="button" className="btn-secondary" style={{ padding: "3px 8px", fontSize: "0.72rem" }} onClick={() => { }}>
          <Archive size={12} aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
