"""
Shared text utilities for Humble Library Sync.
"""

import re


def normalize_title(title: str) -> str:
    """Lowercases, strips punctuation, and collapses whitespace for fuzzy matching."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()