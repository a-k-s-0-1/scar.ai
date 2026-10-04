"""General helper utilities for hashing, formatting, and calculations."""

import hashlib


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of normalized text for deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_url_domain(url: str) -> str:
    """Extract lowercased domain hostname from URL string."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""
