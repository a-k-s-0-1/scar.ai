"use client";

// Interactive knowledge-graph visualization (IKF layer output).
// Renders /api/research/{id}/knowledge via vis-network. Caps rendered nodes
// to keep the physics simulation fast (see IMPLEMENTATION.md risk notes).

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ExternalLink, X } from "lucide-react";
import { getKnowledgeGraph } from "@/lib/api";
import { useTheme } from "@/lib/preferences";

const MAX_NODES = 50;

// Node colours come from the theme's chart tokens so the graph stays legible in
// both light and dark mode. vis-network needs literal colours, so the tokens are
// read from the document at render time.
const TYPE_TOKENS: Record<string, string> = {
  entity: "--chart-1",
  concept: "--chart-2",
  person: "--chart-3",
  place: "--chart-4",
  event: "--chart-5",
  default: "--chart-neutral",
};

function readToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

interface SelectedNode {
  id: string;
  label: string;
  entityType?: string;
}

interface EntityEntry {
  id: string;
  label: string;
  entityType?: string;
  degree: number;
}

function googleSearchUrl(label: string): string {
  return `https://www.google.com/search?q=${encodeURIComponent(label)}`;
}

export function KnowledgeGraphView({ sessionId }: { sessionId: string }) {
  const { resolved } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const [stats, setStats] = useState<{
    shown: number;
    total: number;
    edges: number;
    entities: EntityEntry[];
  } | null>(null);

  // Re-runs whenever the session or the colour theme changes.
  useEffect(() => {
    let disposed = false;
    let cleanup: (() => void) | undefined;

    async function render() {
      try {
        const graph = await getKnowledgeGraph(sessionId);
        if (disposed) return;
        // Loaded graph replaces whatever node was previously selected.
        setSelected(null);

        const nodes = graph.nodes || [];
        if (nodes.length === 0) {
          setStats({
            shown: 0,
            total: 0,
            edges: graph.edges?.length || 0,
            entities: [],
          });
          setLoading(false);
          return;
        }

        // Rank nodes by degree (connections) so the cap keeps the most connected.
        const degree = new Map<string, number>();
        for (const e of graph.edges || []) {
          degree.set(e.from_node, (degree.get(e.from_node) || 0) + 1);
          degree.set(e.to_node, (degree.get(e.to_node) || 0) + 1);
        }
        const keptIds = new Set(
          [...nodes]
            .sort((a, b) => (degree.get(b.id) || 0) - (degree.get(a.id) || 0))
            .slice(0, MAX_NODES)
            .map((n) => n.id)
        );
        const kept = nodes.filter((n) => keptIds.has(n.id));
        const keptEdges = (graph.edges || []).filter(
          (e) => keptIds.has(e.from_node) && keptIds.has(e.to_node)
        );
        setStats({
          shown: kept.length,
          total: nodes.length,
          edges: keptEdges.length,
          entities: [...kept]
            .map((n) => ({
              id: n.id,
              label: n.label,
              entityType: n.entity_type,
              degree: degree.get(n.id) || 0,
            }))
            .sort((a, b) => b.degree - a.degree),
        });

        const vis = await import("vis-network/standalone");
        if (disposed || !containerRef.current) return;

        const nodeFontColor = readToken("--text-primary", "#e2e8f0");
        const edgeColor = readToken("--chart-neutral", "#8e6c99");
        const edgeHighlight = readToken("--accent", "#9b71b2");
        const edgeFontColor = readToken("--text-muted", "#8e6c99");

        const visNodes = new vis.DataSet(
          kept.map((n) => ({
            id: n.id,
            label: n.label.length > 28 ? n.label.slice(0, 26) + "…" : n.label,
            title: `${n.label}${n.entity_type ? ` (${n.entity_type})` : ""}`,
            color:
              readToken(
                TYPE_TOKENS[n.entity_type || ""] || TYPE_TOKENS.default,
                "#9b71b2"
              ),
            font: { color: nodeFontColor, size: 12, face: "Inter, sans-serif" },
            shape: "dot",
            size: Math.min(24, 8 + (degree.get(n.id) || 0) * 2),
          }))
        );
        const visEdges = new vis.DataSet(
          keptEdges.map((e) => ({
            id: e.id,
            from: e.from_node,
            to: e.to_node,
            label: e.label && e.label.length <= 20 ? e.label : undefined,
            color: { color: edgeColor, highlight: edgeHighlight },
            font: { size: 9, color: edgeFontColor },
          }))
        );

        const network = new vis.Network(
          containerRef.current,
          { nodes: visNodes, edges: visEdges },
          {
            physics: {
              solver: "barnesHut",
              barnesHut: { gravitationalConstant: -2200, springLength: 110 },
              stabilization: { iterations: 180 },
            },
            interaction: { hover: true, tooltipDelay: 120, navigationButtons: false },
          }
        );

        // Clicking a node opens the action panel under the canvas.
        network.on("click", (params: { nodes?: Array<string | number> }) => {
          const clicked = params.nodes?.[0];
          if (clicked === undefined) {
            setSelected(null);
            return;
          }
          const node = kept.find((n) => n.id === String(clicked));
          setSelected(
            node
              ? { id: node.id, label: node.label, entityType: node.entity_type }
              : null
          );
        });

        cleanup = () => network.destroy();
        setLoading(false);
      } catch (e) {
        if (!disposed) {
          setError(e instanceof Error ? e.message : "Failed to load knowledge graph");
          setLoading(false);
        }
      }
    }

    render();
    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [sessionId, resolved]);

  const closePanel = useCallback(() => setSelected(null), []);

  const selectedSearchUrl = selected ? googleSearchUrl(selected.label) : "";

  return (
    <div>
      <div
        ref={containerRef}
        className="card"
        style={{
          height: 420,
          borderRadius: 16,
          position: "relative",
          overflow: "hidden",
        }}
      />

      {selected && (
        <div
          className="graph-panel"
          role="group"
          aria-label={`Actions for ${selected.label}`}
        >
          <span style={{ minWidth: 0, maxWidth: 200 }}>
            <span
              style={{
                display: "block",
                fontSize: "0.78rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {selected.label}
            </span>
            {selected.entityType && (
              <span
                style={{
                  display: "block",
                  fontSize: "0.66rem",
                  color: "var(--text-muted)",
                  textTransform: "capitalize",
                }}
              >
                {selected.entityType}
              </span>
            )}
          </span>
          <a
            className="btn-secondary"
            href={selectedSearchUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{ padding: "6px 10px", fontSize: "0.75rem", textDecoration: "none" }}
          >
            <ExternalLink size={12} aria-hidden="true" />
            Search on Google
          </a>
          <button
            type="button"
            className="icon-button"
            onClick={closePanel}
            aria-label="Close node actions"
            style={{ width: 26, height: 26 }}
          >
            <X size={14} aria-hidden="true" />
          </button>
        </div>
      )}

      {loading && (
        <div
          className="card shimmer"
          style={{ height: 420, borderRadius: 16, marginTop: -436 }}
        />
      )}

      {!loading && error && (
        <p
          style={{
            color: "var(--danger)",
            fontSize: "0.85rem",
            marginTop: 8,
            display: "flex",
            gap: 6,
            alignItems: "flex-start",
          }}
        >
          <AlertTriangle size={15} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
          Could not load knowledge graph: {error}
        </p>
      )}

      {!loading && !error && stats && stats.total === 0 && (
        <p
          style={{
            color: "var(--text-muted)",
            fontSize: "0.85rem",
            marginTop: -404,
            padding: 16,
          }}
        >
          No knowledge graph yet — nodes appear once claims are fused.
        </p>
      )}

      {!loading && !error && stats && stats.total > 0 && (
        <p
          style={{
            color: "var(--text-muted)",
            fontSize: "0.78rem",
            marginTop: 8,
          }}
        >
          <span className="mono-num">
            Showing {stats.shown} most-connected entities of {stats.total} (
            {stats.edges} relationships)
          </span>
          {stats.total > MAX_NODES &&
            ` — ${stats.total - MAX_NODES} smaller nodes hidden for clarity.`}{" "}
          Select any node to search it on Google, or pick an entity from the list
          below.
        </p>
      )}

      {/* Canvas nodes cannot be reached by keyboard or screen readers, so the
          same entity set is available as a text list with the same action. */}
      {!loading && !error && stats && (stats.entities?.length ?? 0) > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary
            style={{
              cursor: "pointer",
              fontSize: "0.78rem",
              fontWeight: 600,
              color: "var(--text-secondary)",
            }}
          >
            Entity index ({stats.entities.length}) — same entities as the graph
          </summary>
          <ul
            style={{
              listStyle: "none",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
              gap: 8,
              padding: 0,
              marginTop: 10,
              maxHeight: 220,
              overflowY: "auto",
            }}
          >
            {stats.entities.map((entity) => (
              <li
                key={entity.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "7px 10px",
                  borderRadius: 9,
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--border)",
                }}
              >
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span
                    style={{
                      display: "block",
                      fontSize: "0.78rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {entity.label}
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontSize: "0.66rem",
                      color: "var(--text-muted)",
                      textTransform: "capitalize",
                    }}
                  >
                    {entity.entityType || "entity"} · {entity.degree} links
                  </span>
                </span>
                <a
                  href={googleSearchUrl(entity.label)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="icon-button"
                  aria-label={`Search ${entity.label} on Google`}
                  title={`Search ${entity.label} on Google`}
                  style={{ width: 26, height: 26, flexShrink: 0 }}
                >
                  <ExternalLink size={13} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
