import { test } from "node:test";
import assert from "node:assert/strict";
import { sanitizeSearchQuery, sanitizeExternalUrl } from "./sanitize.ts";

test("sanitizeSearchQuery removes control characters and zero-width spaces", () => {
  const dirty = "Quantum\x00\x1F computing\u200B basics";
  assert.equal(sanitizeSearchQuery(dirty), "Quantum computing basics");
});

test("sanitizeSearchQuery limits query length to 500 characters", () => {
  const longInput = "a".repeat(700);
  assert.equal(sanitizeSearchQuery(longInput).length, 500);
});

test("sanitizeSearchQuery normalizes whitespace and trims", () => {
  const whitespace = "   deep   learning    in   genomics   ";
  assert.equal(sanitizeSearchQuery(whitespace), "deep learning in genomics");
});

test("sanitizeSearchQuery returns empty string for null or undefined", () => {
  assert.equal(sanitizeSearchQuery(null), "");
  assert.equal(sanitizeSearchQuery(undefined), "");
});

test("sanitizeExternalUrl allows valid http and https URLs", () => {
  assert.equal(sanitizeExternalUrl("https://github.com"), "https://github.com/");
  assert.equal(sanitizeExternalUrl("http://example.com/docs"), "http://example.com/docs");
});

test("sanitizeExternalUrl blocks dangerous javascript and data protocols", () => {
  assert.equal(sanitizeExternalUrl("javascript:alert(1)"), "#");
  assert.equal(sanitizeExternalUrl("data:text/html,<script>alert(1)</script>"), "#");
  assert.equal(sanitizeExternalUrl("vbscript:msgbox(1)"), "#");
  assert.equal(sanitizeExternalUrl("invalid-url"), "#");
});
