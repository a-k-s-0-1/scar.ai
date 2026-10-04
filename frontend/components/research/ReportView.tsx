"use client";

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Download,
  FileText,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { buildReportPdf, downloadBlob, reportPdfFilename } from "@/lib/pdf";
import type { ResearchReport } from "@/lib/types";

const EVIDENCE_PREVIEW_COUNT = 15;
/** Mirrors the backend's MAX_SYNTHESIS_RETRIES. */
const MAX_SYNTHESIS_RETRIES = 3;
/** Keeps prose lines at a comfortable measure instead of full card width. */
const READING_MEASURE = 720;
/** Clears the sticky section nav when jumping to a heading. */
const SCROLL_MARGIN = 72;

type SectionKey =
  | "summary"
  | "findings"
  | "evidence"
  | "versions"
  | "contradictions"
  | "gaps"
  | "sources";

interface SectionDef {
  key: SectionKey;
  label: string;
  count?: number;
}

const ALL_SECTIONS: SectionDef[] = [
  { key: "summary", label: "Summary" },
  { key: "findings", label: "Key findings" },
  { key: "evidence", label: "Evidence" },
  { key: "versions", label: "Over time" },
  { key: "contradictions", label: "Conflicts" },
  { key: "gaps", label: "Gaps" },
  { key: "sources", label: "Sources" },
];

function SectionHeading({
  label,
  count,
  tone,
  hint,
}: {
  label: string;
  count?: number;
  tone: string;
  hint?: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <h4
          style={{
            fontSize: "0.75rem",
            fontWeight: 700,
            color: tone,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
          }}
        >
          {label}
          {count !== undefined ? ` (${count})` : ""}
        </h4>
        <span
          aria-hidden="true"
          style={{ flex: 1, height: 1, background: "var(--border)" }}
        />
      </div>
      {hint && (
        <p
          style={{
            marginTop: 6,
            fontSize: "0.74rem",
            color: "var(--text-muted)",
            lineHeight: 1.5,
          }}
        >
          {hint}
        </p>
      )}
    </div>
  );
}

function NavChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "true" : undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "5px 11px",
        borderRadius: 999,
        fontSize: "0.75rem",
        fontWeight: 600,
        cursor: "pointer",
        whiteSpace: "nowrap",
        color: active ? "var(--accent-ink)" : "var(--text-muted)",
        background: active ? "var(--accent-soft)" : "transparent",
        border: `1px solid ${active ? "var(--accent-border)" : "var(--border)"}`,
      }}
    >
      {label}
      {count !== undefined && (
        <span className="mono-num" style={{ fontSize: "0.7rem", opacity: 0.75 }}>
          {count}
        </span>
      )}
    </button>
  );
}

export function ReportView({
  report,
  onRetrySynthesis,
}: {
  report: ResearchReport;
  /**
   * Re-runs only the summary step over evidence already gathered. Omit it where
   * there is no session to retry against.
   */
  onRetrySynthesis?: () => Promise<void>;
}) {
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const [claimQuery, setClaimQuery] = useState("");
  const [activeSection, setActiveSection] = useState<SectionKey | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [retryingSynthesis, setRetryingSynthesis] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  // The card element itself is the scroll anchor for the sticky section nav.
  const contentRef = useRef<HTMLDivElement | null>(null);

  const evidence = useMemo(() => report.evidence_table ?? [], [report]);
  const sourcesList = useMemo(
    () =>
      report.citations && report.citations.length > 0
        ? report.citations.map((c) => ({
            id: c.source_id,
            url: c.url,
            title: c.title || c.url,
            credibility_score: c.credibility_score,
            number: c.citation_number,
          }))
        : (report.sources || []).map((s, idx) => ({
            id: s.id,
            url: s.url,
            title: s.title || s.url,
            credibility_score: s.credibility_score,
            number: idx + 1,
          })),
    [report]
  );

  const gaps = useMemo(
    () => report.unknowns || report.gaps_identified || [],
    [report]
  );
  const keyFindings = useMemo(() => report.key_findings || [], [report]);
  const contradictions = useMemo(() => report.contradictions ?? [], [report]);
  const meta = report.metadata;
  const totalSources = meta?.total_sources ?? sourcesList.length;
  const totalClaims = meta?.total_claims ?? evidence.length;
  const synthesisFallback = meta?.synthesis === "fallback";
  const synthesisRetryCount = meta?.retry_count ?? 0;

  const normalizedQuery = claimQuery.trim().toLowerCase();
  const matchingEvidence = useMemo(() => {
    if (!normalizedQuery) return evidence;
    return evidence.filter((item) =>
      [item.claim, item.confidence, ...(item.citations ?? [])]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery)
    );
  }, [evidence, normalizedQuery]);

  const filtered = normalizedQuery.length > 0;
  const visibleEvidence = showAllEvidence
    ? matchingEvidence
    : matchingEvidence.slice(0, EVIDENCE_PREVIEW_COUNT);
  const hiddenEvidenceCount = matchingEvidence.length - visibleEvidence.length;

  // Reading aid: how the extracted claims split across confidence bands.
  const confidenceMix = useMemo(() => {
    const mix = { high: 0, medium: 0, low: 0 };
    for (const item of evidence) {
      if (item.confidence === "high") mix.high += 1;
      else if (item.confidence === "medium") mix.medium += 1;
      else if (item.confidence === "low") mix.low += 1;
    }
    return mix;
  }, [evidence]);

  // IKF 2.0: the same split, but by what the *evidence* supports rather than by how
  // sure the extractor sounded. Absent on reports written before the upgrade.
  const evidenceMix = useMemo(() => {
    const mix = { high: 0, medium: 0, low: 0 };
    for (const item of evidence) {
      if (item.evidence_band === "high") mix.high += 1;
      else if (item.evidence_band === "medium") mix.medium += 1;
      else if (item.evidence_band === "low") mix.low += 1;
    }
    return mix;
  }, [evidence]);

  const versions = useMemo(() => report.versions ?? [], [report]);
  const evidenceBandTotal = evidenceMix.high + evidenceMix.medium + evidenceMix.low;

  const sections = useMemo<SectionDef[]>(
    () =>
      ALL_SECTIONS.map((section) => {
        if (section.key === "summary") {
          return report.executive_summary ? section : null;
        }
        if (section.key === "findings") {
          return keyFindings.length > 0
            ? { ...section, count: keyFindings.length }
            : null;
        }
        if (section.key === "evidence") {
          return evidence.length > 0
            ? { ...section, count: evidence.length }
            : null;
        }
        if (section.key === "versions") {
          return versions.length > 0
            ? { ...section, count: versions.length }
            : null;
        }
        if (section.key === "contradictions") {
          return contradictions.length > 0 || report.contradictions_summary
            ? { ...section, count: contradictions.length || undefined }
            : null;
        }
        if (section.key === "gaps") {
          return gaps.length > 0 ? { ...section, count: gaps.length } : null;
        }
        return sourcesList.length > 0
          ? { ...section, count: sourcesList.length }
          : null;
      }).filter((section): section is SectionDef => section !== null),
    [
      report.executive_summary,
      report.contradictions_summary,
      keyFindings.length,
      evidence.length,
      versions.length,
      contradictions.length,
      gaps.length,
      sourcesList.length,
    ]
  );

  // Highlight the section the reader is currently in.
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const container = contentRef.current;
    if (!container) return;
    const nodes = Array.from(
      container.querySelectorAll<HTMLElement>("[data-section]")
    );
    if (nodes.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const topEntry = entries
          .filter((entry) => entry.isIntersecting)
          .sort(
            (a, b) => a.boundingClientRect.top - b.boundingClientRect.top
          )[0];
        const key = topEntry?.target.getAttribute("data-section");
        if (key) setActiveSection(key as SectionKey);
      },
      { rootMargin: "-15% 0px -70% 0px", threshold: 0 }
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [sections]);

  const jumpTo = useCallback((key: SectionKey) => {
    const node = contentRef.current?.querySelector<HTMLElement>(
      `[data-section="${key}"]`
    );
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveSection(key);
  }, []);

  const handleRetrySynthesis = useCallback(() => {
    if (!onRetrySynthesis || retryingSynthesis) return;
    setRetryingSynthesis(true);
    setRetryError(null);
    onRetrySynthesis()
      .catch((error: unknown) => {
        setRetryError(
          error instanceof Error
            ? error.message
            : "The synthesis retry failed."
        );
      })
      .finally(() => setRetryingSynthesis(false));
  }, [onRetrySynthesis, retryingSynthesis]);

  const handleExportPdf = useCallback(() => {
    if (exporting) return;
    setExporting(true);
    setExportError(null);
    // Yield one frame so the button can paint its busy state before we build
    // the document synchronously.
    window.setTimeout(() => {
      try {
        downloadBlob(buildReportPdf(report), reportPdfFilename(report));
      } catch {
        setExportError("This report could not be turned into a PDF.");
      } finally {
        setExporting(false);
      }
    }, 0);
  }, [exporting, report]);

  const sectionStyle: React.CSSProperties = {
    marginBottom: 28,
    scrollMarginTop: SCROLL_MARGIN,
  };

  return (
    <div
      ref={contentRef}
      className="card animate-fade-in-up"
      style={{ padding: "24px 28px" }}
    >
      {/* Title block */}
      <div style={{ marginBottom: 18 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: "0.68rem",
            fontWeight: 700,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--accent-purple)",
            marginBottom: 8,
          }}
        >
          <FileText size={13} aria-hidden="true" />
          Research report
        </div>
        <h3
          style={{
            fontSize: "1.25rem",
            fontWeight: 700,
            color: "var(--text-primary)",
            marginBottom: 12,
            lineHeight: 1.35,
            maxWidth: READING_MEASURE,
          }}
        >
          {report.question}
        </h3>

        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            alignItems: "center",
            marginBottom: 14,
          }}
        >
          <span className="badge badge-blue">{totalSources} sources</span>
          <span className="badge badge-purple">{totalClaims} claims</span>
          {report.depth && (
            <span className="badge badge-gray">{report.depth} depth</span>
          )}
          {meta?.total_nodes ? (
            <span className="badge badge-green">{meta.total_nodes} entities</span>
          ) : null}
          {typeof meta?.coverage === "number" && (
            <span className="badge badge-gray">
              {Math.round(meta.coverage * 100)}% coverage
            </span>
          )}
        </div>

        <div
          style={{
            display: "flex",
            gap: 10,
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <button
            type="button"
            className="btn-glow"
            onClick={handleExportPdf}
            disabled={exporting}
            title="Builds an A4 PDF of this report in your browser — no backend needed."
            style={{
              padding: "8px 16px",
              fontSize: "0.82rem",
              display: "inline-flex",
              alignItems: "center",
              gap: 7,
            }}
          >
            <Download size={14} aria-hidden="true" />
            {exporting ? "Preparing PDF…" : "Download PDF"}
          </button>
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
            {[
              meta?.iterations_completed
                ? `${meta.iterations_completed} iterations`
                : null,
              meta?.generated_at ?? null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>

        {exportError && (
          <p
            style={{
              marginTop: 8,
              fontSize: "0.75rem",
              color: "var(--danger)",
              display: "flex",
              gap: 6,
              alignItems: "flex-start",
            }}
          >
            <AlertTriangle
              size={14}
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: 2 }}
            />
            {exportError}
          </p>
        )}

        {synthesisFallback && (
          <div
            style={{
              marginTop: 10,
              padding: "10px 14px",
              borderRadius: 10,
              background: "var(--warn-soft)",
              border: "1px solid var(--warn-border)",
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              flexWrap: "wrap",
            }}
          >
            <AlertTriangle
              size={15}
              aria-hidden="true"
              style={{
                flexShrink: 0,
                marginTop: 2,
                color: "var(--warn)",
              }}
            />
            <div style={{ flex: 1, minWidth: 220 }}>
              <p
                style={{
                  fontSize: "0.8rem",
                  fontWeight: 700,
                  color: "var(--warn)",
                  marginBottom: 3,
                }}
              >
                Low-confidence synthesis
              </p>
              <p
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                }}
              >
                {synthesisRetryCount > 0
                  ? `Retried ${synthesisRetryCount} of ${MAX_SYNTHESIS_RETRIES} times; `
                  : ""}
                the language model was unavailable, so this summary is
                deterministic — the findings below are the extracted claims
                themselves. A retry costs one model call over the evidence
                already gathered and starts no new web research.
              </p>
              {retryError && (
                <p
                  style={{
                    marginTop: 4,
                    fontSize: "0.74rem",
                    color: "var(--danger)",
                  }}
                >
                  {retryError}
                </p>
              )}
            </div>
            {onRetrySynthesis && (
              <button
                type="button"
                className="btn-glow"
                onClick={handleRetrySynthesis}
                disabled={
                  retryingSynthesis ||
                  synthesisRetryCount >= MAX_SYNTHESIS_RETRIES
                }
                style={{
                  padding: "8px 14px",
                  fontSize: "0.8rem",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <RefreshCw size={13} aria-hidden="true" />
                {retryingSynthesis
                  ? "Re-synthesizing…"
                  : synthesisRetryCount >= MAX_SYNTHESIS_RETRIES
                  ? "Retry limit reached"
                  : "Retry synthesis"}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Jump navigation — sticks to the top while the reader scrolls. */}
      {sections.length > 1 && (
        <nav
          aria-label="Report sections"
          style={{
            position: "sticky",
            top: 0,
            zIndex: 5,
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            padding: "10px 0",
            marginBottom: 20,
            background: "var(--bg-card)",
            borderBottom: "1px solid var(--border)",
          }}
        >
          {sections.map((section) => (
            <NavChip
              key={section.key}
              label={section.label}
              count={section.count}
              active={activeSection === section.key}
              onClick={() => jumpTo(section.key)}
            />
          ))}
        </nav>
      )}

      {/* Executive summary */}
      {report.executive_summary && (
        <section
          data-section="summary"
          style={sectionStyle}
        >
          <SectionHeading label="Executive Summary" tone="var(--accent-purple)" />
          <p
            style={{
              fontSize: "0.95rem",
              color: "var(--text-secondary)",
              lineHeight: 1.75,
              maxWidth: READING_MEASURE,
              background: "var(--accent-soft)",
              border: "1px solid var(--accent-border)",
              borderRadius: 10,
              padding: "16px 20px",
            }}
          >
            {report.executive_summary}
          </p>
        </section>
      )}

      {/* Key findings */}
      {keyFindings.length > 0 && (
        <section
          data-section="findings"
          style={sectionStyle}
        >
          <SectionHeading
            label="Key Findings"
            count={keyFindings.length}
            tone="var(--ok)"
          />
          <ol
            style={{
              listStyle: "none",
              display: "flex",
              flexDirection: "column",
              gap: 10,
              padding: 0,
              maxWidth: READING_MEASURE,
            }}
          >
            {keyFindings.map((finding, i) => (
              <li
                key={i}
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  fontSize: "0.9rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.65,
                  padding: "11px 15px",
                  borderRadius: 8,
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--border)",
                }}
              >
                <span
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: "50%",
                    background: "var(--ok-soft)",
                    color: "var(--ok)",
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: 2,
                  }}
                >
                  {i + 1}
                </span>
                <span style={{ flex: 1 }}>{finding}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Evidence */}
      {evidence.length > 0 && (
        <section
          data-section="evidence"
          style={sectionStyle}
        >
          <SectionHeading
            label="Evidence & Fact Extraction"
            count={evidence.length}
            tone="var(--info)"
            hint={
              evidenceBandTotal > 0
                ? `Evidence strength — high ${evidenceMix.high}, medium ${evidenceMix.medium}, low ${evidenceMix.low} (weighted by source quality, independent support, recency, agreement and extraction confidence).`
                : confidenceMix.high + confidenceMix.medium + confidenceMix.low > 0
                  ? `Confidence spread — high ${confidenceMix.high}, medium ${confidenceMix.medium}, low ${confidenceMix.low}.`
                  : undefined
            }
          />

          <div
            style={{
              display: "flex",
              gap: 8,
              flexWrap: "wrap",
              alignItems: "center",
              marginBottom: 12,
            }}
          >
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                padding: "6px 11px",
                borderRadius: 8,
                border: "1px solid var(--border)",
                background: "var(--bg-inset)",
                fontSize: "0.78rem",
                color: "var(--text-muted)",
                flex: "1 1 240px",
                maxWidth: 360,
              }}
            >
              <Search size={13} aria-hidden="true" />
              <input
                type="search"
                value={claimQuery}
                onChange={(event) => setClaimQuery(event.target.value)}
                placeholder="Filter claims and citations…"
                aria-label="Filter claims"
                style={{
                  border: "none",
                  background: "transparent",
                  outline: "none",
                  color: "var(--text-primary)",
                  fontSize: "0.8rem",
                  width: "100%",
                }}
              />
              {claimQuery && (
                <button
                  type="button"
                  onClick={() => setClaimQuery("")}
                  aria-label="Clear filter"
                  style={{
                    border: "none",
                    background: "none",
                    cursor: "pointer",
                    color: "var(--text-muted)",
                    display: "inline-flex",
                    padding: 0,
                  }}
                >
                  <X size={13} aria-hidden="true" />
                </button>
              )}
            </label>

            {filtered && (
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                {matchingEvidence.length} of {evidence.length} claims match
              </span>
            )}

            {(hiddenEvidenceCount > 0 || showAllEvidence) &&
              evidence.length > EVIDENCE_PREVIEW_COUNT && (
                <button
                  type="button"
                  onClick={() => setShowAllEvidence((value) => !value)}
                  className="btn-secondary"
                  style={{
                    padding: "6px 12px",
                    fontSize: "0.75rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                  }}
                >
                  {showAllEvidence ? (
                    <>
                      <ChevronUp size={13} aria-hidden="true" />
                      Collapse to first {EVIDENCE_PREVIEW_COUNT}
                    </>
                  ) : (
                    <>
                      <ChevronDown size={13} aria-hidden="true" />
                      Show all {matchingEvidence.length} claims
                    </>
                  )}
                </button>
              )}
          </div>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
              maxHeight: 460,
              overflowY: "auto",
              paddingRight: 4,
            }}
          >
            {visibleEvidence.map((item, idx) => (
              <div
                key={item.claim_id || idx}
                style={{
                  padding: "11px 15px",
                  borderRadius: 8,
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--border)",
                  fontSize: "0.86rem",
                  lineHeight: 1.6,
                }}
              >
                <div style={{ color: "var(--text-primary)", marginBottom: 5 }}>
                  {item.claim}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 10,
                    alignItems: "center",
                    flexWrap: "wrap",
                    fontSize: "0.72rem",
                  }}
                >
                  <span
                    style={{
                      color:
                        item.confidence === "high"
                          ? "var(--ok)"
                          : item.confidence === "medium"
                          ? "var(--warn)"
                          : "var(--danger)",
                      fontWeight: 600,
                    }}
                  >
                    Confidence: {item.confidence}
                  </span>
                  {item.citations && item.citations.length > 0 && (
                    <span style={{ color: "var(--text-muted)" }}>
                      Citations: {item.citations.map((c) => `[${c}]`).join(" ")}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {visibleEvidence.length === 0 && (
              <p
                style={{
                  fontSize: "0.84rem",
                  color: "var(--text-muted)",
                  padding: "10px 2px",
                }}
              >
                No claim matches “{claimQuery}”.
              </p>
            )}
          </div>
        </section>
      )}

      {/* Facts that moved over time rather than disagreeing */}
      {versions.length > 0 && (
        <section data-section="versions" style={sectionStyle}>
          <SectionHeading
            label="Facts over time"
            count={versions.length}
            tone="var(--accent-ink)"
            hint="The same fact observed at different dates. These are intentionally kept out of the conflicts list — only claims about the same period with incompatible values are disagreements."
          />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              maxWidth: READING_MEASURE,
            }}
          >
            {versions.map((group) => (
              <div
                key={`${group.subject}:${group.predicate}`}
                className="card"
                style={{ padding: "12px 14px" }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                    alignItems: "baseline",
                    flexWrap: "wrap",
                  }}
                >
                  <span
                    style={{
                      fontSize: "0.85rem",
                      fontWeight: 700,
                      color: "var(--text-primary)",
                    }}
                  >
                    {group.subject} · {group.predicate}
                  </span>
                  <span
                    className="mono-num"
                    style={{
                      fontSize: "0.72rem",
                      color:
                        group.status === "conflicted"
                          ? "var(--danger)"
                          : "var(--text-muted)",
                    }}
                  >
                    {group.span.from && group.span.to
                      ? `${group.span.from} → ${group.span.to}`
                      : "undated"}
                    {group.status === "conflicted" ? " · conflicting" : ""}
                  </span>
                </div>
                <ol
                  style={{
                    listStyle: "none",
                    padding: 0,
                    marginTop: 8,
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  {group.versions.map((version) => (
                    <li
                      key={version.claim_id}
                      style={{
                        display: "flex",
                        gap: 10,
                        alignItems: "baseline",
                        fontSize: "0.82rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.5,
                      }}
                    >
                      <span
                        className="mono-num"
                        style={{
                          color: "var(--text-muted)",
                          minWidth: 38,
                          flexShrink: 0,
                        }}
                      >
                        {version.valid_to ?? version.valid_from ?? "—"}
                      </span>
                      <span style={{ flex: 1 }}>{version.text}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Contradictions */}
      {(contradictions.length > 0 || report.contradictions_summary) && (
        <section
          data-section="contradictions"
          style={sectionStyle}
        >
          <SectionHeading
            label="Contradictions and conflicts"
            count={contradictions.length || undefined}
            tone="var(--warn)"
          />
          {contradictions.length > 0 ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 8,
                maxWidth: READING_MEASURE,
              }}
            >
              {contradictions.map((c, i) => (
                <div
                  key={c.id || i}
                  style={{
                    padding: "12px 16px",
                    borderRadius: 8,
                    background: "var(--warn-soft)",
                    border: "1px solid var(--warn-border)",
                    fontSize: "0.86rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.6,
                  }}
                >
                  <div
                    style={{
                      fontWeight: 600,
                      color: "var(--warn)",
                      marginBottom: 5,
                      textTransform: "capitalize",
                    }}
                  >
                    Severity: {c.severity}
                  </div>
                  {c.claim_1 && (
                    <div style={{ marginBottom: 2 }}>
                      <strong>Claim A:</strong> {c.claim_1}
                    </div>
                  )}
                  {c.claim_2 && (
                    <div style={{ marginBottom: 4 }}>
                      <strong>Claim B:</strong> {c.claim_2}
                    </div>
                  )}
                  {c.explanation && (
                    <div
                      style={{
                        color: "var(--text-muted)",
                        fontStyle: "italic",
                      }}
                    >
                      {c.explanation}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 10,
                background: "var(--warn-soft)",
                border: "1px solid var(--warn-border)",
                fontSize: "0.88rem",
                color: "var(--text-secondary)",
                lineHeight: 1.65,
                maxWidth: READING_MEASURE,
              }}
            >
              {report.contradictions_summary}
            </div>
          )}
        </section>
      )}

      {/* Gaps */}
      {gaps.length > 0 && (
        <section
          data-section="gaps"
          style={sectionStyle}
        >
          <SectionHeading
            label="Knowledge Gaps & Open Unknowns"
            count={gaps.length}
            tone="var(--info)"
          />
          <ul
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              padding: 0,
              listStyle: "none",
              maxWidth: READING_MEASURE,
            }}
          >
            {gaps.map((gap, i) => (
              <li
                key={i}
                style={{
                  padding: "7px 13px",
                  borderRadius: 8,
                  background: "var(--info-soft)",
                  border: "1px solid var(--info-border)",
                  color: "var(--info)",
                  fontSize: "0.84rem",
                  lineHeight: 1.45,
                }}
              >
                {gap}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Sources */}
      {sourcesList.length > 0 && (
        <section
          data-section="sources"
          style={{ ...sectionStyle, marginBottom: 0 }}
        >
          <SectionHeading
            label="Citations & Sources"
            count={sourcesList.length}
            tone="var(--text-secondary)"
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {sourcesList.map((source) => (
              <div
                key={source.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 14px",
                  borderRadius: 8,
                  background: "var(--bg-subtle)",
                  border: "1px solid var(--border)",
                }}
              >
                <span
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: 6,
                    background: "var(--accent-soft)",
                    color: "var(--accent-ink)",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {source.number}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      fontSize: "0.86rem",
                      fontWeight: 600,
                      color: "var(--info)",
                      textDecoration: "none",
                      display: "block",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {source.title}
                  </a>
                  <div
                    style={{
                      fontSize: "0.72rem",
                      color: "var(--text-muted)",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {source.url}
                  </div>
                </div>
                <div
                  style={{
                    flexShrink: 0,
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    color:
                      source.credibility_score >= 0.7
                        ? "var(--ok)"
                        : source.credibility_score >= 0.5
                        ? "var(--warn)"
                        : "var(--danger)",
                    background:
                      source.credibility_score >= 0.7
                        ? "var(--ok-soft)"
                        : source.credibility_score >= 0.5
                        ? "var(--warn-soft)"
                        : "var(--danger-soft)",
                    padding: "3px 9px",
                    borderRadius: 6,
                  }}
                >
                  {Math.round(source.credibility_score * 100)}% Credibility
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
