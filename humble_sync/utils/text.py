"""
Shared text utilities for Humble Library Sync.
"""

import re
from difflib import SequenceMatcher


def normalize_title(title: str) -> str:
    """Lowercases, strips punctuation, and collapses whitespace for fuzzy matching."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


# ---------------------------------------------------------------------------
# Volume / Series Extraction
# ---------------------------------------------------------------------------

# Patterns matched (case-insensitive), in priority order:
#   1. "Title, Vol. 3" / "Title Vol 3" / "Title, Volume 3"
#   2. "Title, Book 2" / "Title Book 2"
#   3. "Title, Edition 4" / "Title, 4th Edition" / "Title 3rd Edition"
#   4. "Title (Series #3)" / "Title (#3)"
# Matches: "Title, Vol. 3" / "Title, Volume 3" / "Title, Book 2"
#          "Title, 3rd Edition" / "Title 3rd Edition"
#          "Title Vol 3" / "Title Book 3"
#          "Title (#5)" / "Title (#No. 5)"
_VOLUME_RE = re.compile(
    r",\s*(?:vol(?:ume)?|book|edition)\.?\s*(\d+)"
    r"|,?\s*(\d+)(?:st|nd|rd|th)\s+edition"
    r"|\s+(?:vol(?:ume)?|book|edition)\.?\s*(\d+)"
    r"|\s+\(\s*(?:#|no\.?\s*)?(\d+)\s*\)",
    re.IGNORECASE,
)


def extract_volume_info(title: str) -> tuple[str, str | None]:
    """Parse volume, book, or edition markers from a title.

    Returns
    -------
    tuple[str, str | None]
        A ``(base_title, volume_info)`` pair where *base_title* is the
        original title with the volume/edition segment removed, and
        *volume_info* is the extracted marker string (e.g. ``"Vol. 3"``,
        ``"Book 2"``) or ``None`` if no pattern matched.

    Examples
    --------
    >>> extract_volume_info("Dune, Vol. 2")
    ('Dune', 'Vol. 2')
    >>> extract_volume_info("Foundation Book 3")
    ('Foundation', 'Book 3')
    >>> extract_volume_info("A Story (#5)")
    ('A Story', '#5')
    """
    match = _VOLUME_RE.search(title)
    if not match:
        return title, None

    volume_info = match.group(0).strip().lstrip(", ")
    base_title = title[: match.start()].rstrip(", ").strip()

    return base_title, volume_info


# ---------------------------------------------------------------------------
# Fuzzy Title Matching
# ---------------------------------------------------------------------------


def is_title_match(title_a: str, title_b: str, threshold: float = 0.85) -> bool:
    """Compare two titles using fuzzy sequence matching.

    Normalises both titles (lowercase, strip punctuation/whitespace) and
    applies ``difflib.SequenceMatcher`` to produce a similarity ratio.  If
    either title contains a volume/book marker the extracted base titles are
    compared first — an exact base-title match is considered a positive
    match regardless of the fuzzy ratio.

    Parameters
    ----------
    title_a, title_b:
        Raw title strings to compare.
    threshold:
        Minimum similarity ratio (0–1) required to consider the titles a
        match.  Defaults to ``0.85``.

    Returns
    -------
    bool
        ``True`` when the titles are considered a match.
    """
    norm_a = normalize_title(title_a)
    norm_b = normalize_title(title_b)

    if not norm_a or not norm_b:
        return False

    # Exact normalised match
    if norm_a == norm_b:
        return True

    # Volume-aware base-title comparison
    base_a, vol_a = extract_volume_info(title_a)
    base_b, vol_b = extract_volume_info(title_b)
    norm_base_a = normalize_title(base_a)
    norm_base_b = normalize_title(base_b)

    if vol_a is not None and vol_b is not None and norm_base_a == norm_base_b:
        return True

    # General fuzzy ratio
    ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    return ratio >= threshold
