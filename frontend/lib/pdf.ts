// Minimal, dependency-free PDF writer.
//
// A research report is plain text in a handful of styles, so shipping a PDF
// engine (or round-tripping to a server) would be far more machinery than the
// job needs. This walks a document model, wraps text with an approximate
// Helvetica metric, paginates onto A4 and serialises a valid PDF 1.4 file with
// an xref table. Everything emitted is ASCII: bytes above 0x7F are written as
// octal escapes, which keeps byte offsets (and therefore the xref) exact.
//
// Character widths are estimated rather than read from the full Helvetica
// metrics table — a line may break a character or two early, but text stays
// inside the margins.

import type { ResearchReport } from "./types";

const PAGE_WIDTH = 595.28;
const PAGE_HEIGHT = 841.89;
const MARGIN = 54;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

const COLOR_TEXT = "0.13 0.09 0.13";
const COLOR_MUTED = "0.42 0.35 0.45";
const COLOR_ACCENT = "0.48 0.32 0.57";
const COLOR_RULE = "0.78 0.71 0.82";

const EVIDENCE_LIMIT = 150;

export interface PdfTextItem {
  text: string;
  style: "title" | "subtitle" | "heading" | "body" | "bullet" | "meta";
}

export interface PdfDocument {
  title: string;
  subtitle?: string;
  meta: string[];
  items: PdfTextItem[];
}

/** Typographic characters that exist in WinAnsiEncoding, by code point. */
const WIN_ANSI_SPECIALS: Record<string, number> = {
  "\u2014": 0x97, // em dash
  "\u2013": 0x96, // en dash
  "\u2018": 0x91,
  "\u2019": 0x92,
  "\u201c": 0x93,
  "\u201d": 0x94,
  "\u2022": 0x95, // bullet
  "\u2026": 0x85, // ellipsis
  "\u20ac": 0x80,
  "\u2122": 0x99,
  "\u00a0": 0x20,
};

function toPdfByte(char: string): number {
  const special = WIN_ANSI_SPECIALS[char];
  if (special !== undefined) return special;
  const code = char.codePointAt(0) ?? 0x3f;
  // Latin-1 and low WinAnsi share code points; anything else would render as
  // mojibake with the standard fonts, so it becomes '?'.
  return code <= 0xff ? code : 0x3f;
}

function escapePdfText(text: string): string {
  let out = "";
  for (const char of text) {
    const byte = toPdfByte(char);
    if (byte === 0x28) out += "\\(";
    else if (byte === 0x29) out += "\\)";
    else if (byte === 0x5c) out += "\\\\";
    else if (byte < 32) out += " ";
    else if (byte > 126) out += `\\${byte.toString(8).padStart(3, "0")}`;
    else out += String.fromCharCode(byte);
  }
  return out;
}

const NARROW = new Set([
  "i", "l", "j", "t", "f", "r", "I", ".", ",", ":", ";", "'", "|", "!", "(", ")", "[", "]", "-",
]);
const WIDE = new Set(["m", "w", "M", "W", "@", "%"]);

/** Approximate Helvetica advance width in text-space units. */
function estimateWidth(text: string, size: number, bold: boolean): number {
  let units = 0;
  for (const char of text) {
    if (char === " ") units += 0.28;
    else if (NARROW.has(char)) units += 0.3;
    else if (WIDE.has(char)) units += 0.88;
    else if (char >= "A" && char <= "Z") units += 0.68;
    else if (char >= "0" && char <= "9") units += 0.56;
    else units += 0.52;
  }
  return units * size * (bold ? 1.04 : 1);
}

function wrapText(text: string, size: number, bold: boolean, maxWidth: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 0) return [""];

  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (estimateWidth(candidate, size, bold) <= maxWidth) {
      current = candidate;
      continue;
    }
    if (current) lines.push(current);
    if (estimateWidth(word, size, bold) <= maxWidth) {
      current = word;
      continue;
    }
    // Hard-split a word that cannot fit a line on its own.
    let chunk = "";
    for (const char of word) {
      if (estimateWidth(chunk + char, size, bold) > maxWidth) {
        lines.push(chunk);
        chunk = char;
      } else {
        chunk += char;
      }
    }
    current = chunk;
  }
  if (current) lines.push(current);
  return lines;
}

interface FontSpec {
  font: "F1" | "F2" | "F3";
  size: number;
  color: string;
  bold: boolean;
  leading: number;
  spaceBefore: number;
  indent: number;
}

const STYLES: Record<PdfTextItem["style"], FontSpec> = {
  title: { font: "F2", size: 19, color: COLOR_TEXT, bold: true, leading: 23, spaceBefore: 0, indent: 0 },
  subtitle: { font: "F1", size: 11.5, color: COLOR_TEXT, bold: false, leading: 16, spaceBefore: 6, indent: 0 },
  heading: { font: "F2", size: 12, color: COLOR_ACCENT, bold: true, leading: 15, spaceBefore: 16, indent: 0 },
  body: { font: "F1", size: 9.6, color: COLOR_TEXT, bold: false, leading: 13.4, spaceBefore: 4, indent: 0 },
  bullet: { font: "F1", size: 9.6, color: COLOR_TEXT, bold: false, leading: 13.4, spaceBefore: 4, indent: 14 },
  meta: { font: "F3", size: 8.2, color: COLOR_MUTED, bold: false, leading: 11.5, spaceBefore: 1, indent: 0 },
};

function textOp(text: string, spec: FontSpec, x: number, y: number): string {
  return `BT ${spec.color} rg /${spec.font} ${spec.size} Tf 1 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)} Tm (${escapePdfText(text)}) Tj ET`;
}

function ruleOp(y: number): string {
  return `${COLOR_RULE} RG 0.7 w ${MARGIN} ${y.toFixed(2)} m ${(PAGE_WIDTH - MARGIN).toFixed(2)} ${y.toFixed(2)} l S`;
}

function paginate(doc: PdfDocument): string[][] {
  const pages: string[][] = [];
  let ops: string[] = [];
  let y = PAGE_HEIGHT - MARGIN;

  const startPage = () => {
    pages.push(ops);
    ops = [];
    y = PAGE_HEIGHT - MARGIN;
  };

  const writeLine = (line: string, spec: FontSpec) => {
    // Keep a footer strip free so the page number never overlaps body text.
    if (y - spec.leading < MARGIN + 26) startPage();
    ops.push(textOp(line, spec, MARGIN + spec.indent, y));
    y -= spec.leading;
  };

  const write = (item: PdfTextItem) => {
    const spec = STYLES[item.style];
    y -= spec.spaceBefore;
    for (const line of wrapText(item.text, spec.size, spec.bold, CONTENT_WIDTH - spec.indent)) {
      writeLine(line, spec);
    }
  };

  write({ text: doc.title, style: "title" });
  y -= 8;
  ops.push(ruleOp(y));
  y -= 10;
  if (doc.subtitle) write({ text: doc.subtitle, style: "subtitle" });
  for (const meta of doc.meta) write({ text: meta, style: "meta" });
  for (const item of doc.items) write(item);

  pages.push(ops);
  return pages;
}

function serialize(pages: string[][]): Blob {
  const objects: string[] = [];
  const pageIds: number[] = [];
  const totalPages = pages.length;

  pages.forEach((ops, pageIndex) => {
    const pageId = 6 + pageIndex * 2;
    const contentId = pageId + 1;
    pageIds.push(pageId);

    const footerY = MARGIN - 18;
    ops.push(ruleOp(footerY + 11));
    ops.push(
      textOp(
        `Self-Correcting Agent for Research - SCAR · page ${pageIndex + 1} of ${totalPages}`,
        STYLES.meta,
        MARGIN,
        footerY
      )
    );

    const stream = ops.join("\n");
    objects[contentId] = `${contentId} 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj`;
    objects[pageId] =
      `${pageId} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_WIDTH} ${PAGE_HEIGHT}] ` +
      `/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> ` +
      `/Contents ${contentId} 0 R >>\nendobj`;
  });

  objects[1] = "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj";
  objects[2] =
    `2 0 obj\n<< /Type /Pages /Kids [${pageIds.map((id) => `${id} 0 R`).join(" ")}] ` +
    `/Count ${pageIds.length} >>\nendobj`;
  objects[3] =
    "3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj";
  objects[4] =
    "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj";
  objects[5] =
    "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>\nendobj";

  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  const maxId = objects.length - 1;
  for (let id = 1; id <= maxId; id += 1) {
    offsets[id] = body.length;
    body += `${objects[id]}\n`;
  }

  const xrefOffset = body.length;
  let xref = `xref\n0 ${maxId + 1}\n0000000000 65535 f \n`;
  for (let id = 1; id <= maxId; id += 1) {
    xref += `${String(offsets[id]).padStart(10, "0")} 00000 n \n`;
  }
  const trailer = `trailer\n<< /Size ${maxId + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  return new Blob([body + xref + trailer], { type: "application/pdf" });
}

export function buildPdf(doc: PdfDocument): Blob {
  return serialize(paginate(doc));
}

/** Trigger a browser download for a generated blob. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Let the browser start the download before releasing the object URL.
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

function reportMetaLines(report: ResearchReport): string[] {
  const meta = report.metadata ?? {};
  const coverage =
    typeof meta.coverage === "number" ? `   coverage: ${Math.round(meta.coverage * 100)}%` : "";
  const iterations = meta.iterations_completed ? `   iterations: ${meta.iterations_completed}` : "";
  const entities = meta.total_nodes ? `   entities: ${meta.total_nodes}` : "";
  const edges = meta.total_edges ? `   relationships: ${meta.total_edges}` : "";
  const generated = meta.generated_at ? `   generated: ${meta.generated_at}` : "";

  return [
    `depth: ${report.depth ?? "standard"}${iterations}${coverage}`,
    `sources: ${meta.total_sources ?? report.sources?.length ?? 0}` +
      `   claims: ${meta.total_claims ?? report.evidence_table?.length ?? 0}` +
      entities +
      edges,
    `session: ${report.session_id}${generated}`,
    meta.synthesis === "fallback"
      ? "synthesis: rule-based fallback (LLM synthesis was unavailable for this run)"
      : "synthesis: LLM executive summary",
  ];
}

/** Map a stored research report onto the PDF document model. */
export function buildReportPdf(report: ResearchReport): Blob {
  const items: PdfTextItem[] = [];
  const push = (heading: string) => items.push({ text: heading, style: "heading" });

  if (report.executive_summary) {
    push("Executive summary");
    items.push({ text: report.executive_summary, style: "body" });
  }

  const findings = report.key_findings ?? [];
  if (findings.length > 0) {
    push(`Key findings (${findings.length})`);
    findings.forEach((finding, index) =>
      items.push({ text: `${index + 1}. ${finding}`, style: "bullet" })
    );
  }

  const evidence = report.evidence_table ?? [];
  if (evidence.length > 0) {
    const shown = evidence.slice(0, EVIDENCE_LIMIT);
    push(`Evidence and fact extraction (${evidence.length})`);
    for (const item of shown) {
      items.push({ text: `- ${item.claim}`, style: "bullet" });
      const citations = item.citations?.length
        ? `  [citations: ${item.citations.join(", ")}]`
        : "";
      items.push({ text: `  confidence: ${item.confidence}${citations}`, style: "meta" });
    }
    if (evidence.length > shown.length) {
      items.push({
        text: `${evidence.length - shown.length} further claims are available in the app.`,
        style: "meta",
      });
    }
  }

  const contradictions = report.contradictions ?? [];
  if (contradictions.length > 0 || report.contradictions_summary) {
    push("Contradictions and conflicts");
    if (report.contradictions_summary) {
      items.push({ text: report.contradictions_summary, style: "body" });
    }
    for (const contradiction of contradictions) {
      items.push({
        text: `- [${contradiction.severity}] ${contradiction.claim_1} <> ${contradiction.claim_2}`,
        style: "bullet",
      });
      if (contradiction.explanation) {
        items.push({ text: `  ${contradiction.explanation}`, style: "meta" });
      }
    }
  }

  const gaps = report.unknowns ?? report.gaps_identified ?? [];
  if (gaps.length > 0) {
    push(`Knowledge gaps and open unknowns (${gaps.length})`);
    gaps.forEach((gap) => items.push({ text: `- ${gap}`, style: "bullet" }));
  }

  const citations = report.citations ?? [];
  const sources = report.sources ?? [];
  if (citations.length > 0) {
    push(`Citations and sources (${citations.length})`);
    citations.forEach((source) => {
      items.push({
        text: `[${source.citation_number}] ${source.title || source.url} (${Math.round(
          source.credibility_score * 100
        )}% credibility)`,
        style: "bullet",
      });
      items.push({ text: `    ${source.url}`, style: "meta" });
    });
  } else if (sources.length > 0) {
    push(`Sources (${sources.length})`);
    sources.forEach((source, index) => {
      items.push({
        text: `[${index + 1}] ${source.title || source.url} (${Math.round(
          source.credibility_score * 100
        )}% credibility)`,
        style: "bullet",
      });
      items.push({ text: `    ${source.url}`, style: "meta" });
    });
  }

  return buildPdf({
    title: "Research report",
    subtitle: report.question,
    meta: reportMetaLines(report),
    items,
  });
}

export function reportPdfFilename(report: ResearchReport): string {
  const stamp = new Date().toISOString().slice(0, 10);
  const slug = slugify(report.question || report.session_id) || "research-report";
  return `research-report-${slug}-${stamp}.pdf`;
}
