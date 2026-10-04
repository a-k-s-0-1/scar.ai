"""HTML and text cleaning utilities for source content extraction."""

import re

from bs4 import BeautifulSoup


def clean_html_content(raw_html: str, max_chars: int = 15000) -> str:
    """Extract clean readable text from HTML by removing boilerplate, scripts, and styling."""
    if not raw_html or not raw_html.strip():
        return ""

    try:
        soup = BeautifulSoup(raw_html, "html.parser")

        # Strip scripts, styles, forms, navbars, footers, headers
        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]
        ):
            tag.decompose()

        # Extract text
        text = soup.get_text(separator=" ", strip=True)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Truncate if overly long
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        return text
    except Exception:
        # Fallback to regex-based tag stripping
        clean = re.sub(r"<[^>]+>", " ", raw_html)
        return re.sub(r"\s+", " ", clean).strip()[:max_chars]


def truncate_for_llm(text: str, max_chars: int = 4000) -> str:
    """Safely truncate content string for LLM prompt context window."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[Content truncated for length]"
