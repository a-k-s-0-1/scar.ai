"""Input validation and sanitization for research questions."""

import re


def validate_question(question: str) -> tuple[bool, str]:
    """Validate question meets minimum length, word count and isn't gibberish.

    Returns:
        (is_valid, error_reason)
    """
    cleaned = question.strip()
    if not cleaned:
        return False, "Question cannot be empty."

    if len(cleaned) < 10:
        return False, "Question must be at least 10 characters long."

    words = cleaned.split()
    if len(words) < 3:
        return False, "Question must contain at least 3 words."

    # Check for repeated single character sequences (e.g. "aaaaaa")
    if re.search(r"(.)\1{6,}", cleaned):
        return False, "Question contains repetitive characters."

    # Check that it contains at least some alphanumeric characters
    if not re.search(r"[a-zA-Z0-9]", cleaned):
        return False, "Question must contain alphanumeric words."

    return True, ""
