/**
 * Client-side input sanitization utilities for safe URL and query parameter handling.
 * Protects against XSS, control character injection, and unconstrained string lengths.
 */

const MAX_QUERY_LENGTH = 500;

/**
 * Strips control characters, non-printable sequences, trims whitespace,
 * and caps the string at MAX_QUERY_LENGTH.
 */
export function sanitizeSearchQuery(raw: string | null | undefined): string {
  if (!raw) return "";

  return raw
    // Strip ASCII control characters (0x00-0x1F, 0x7F) and zero-width spaces
    .replace(/[\x00-\x1F\x7F\u200B-\u200D\uFEFF]/g, "")
    // Normalize excessive whitespace
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_QUERY_LENGTH);
}

/**
 * Validates that an external URL strictly belongs to allowed HTTP/HTTPS protocols.
 * Prevents javascript: or data: URI execution.
 */
export function sanitizeExternalUrl(url: string): string {
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return parsed.href;
    }
  } catch {
    // Malformed URL
  }
  return "#";
}
