"""Search and filtering utilities for the Humble Bundle library catalog."""


def search_catalog(items: list[dict], query: str) -> list[dict]:
    """Filter *items* whose title, publisher, or bundle matches *query* (case-insensitive).

    Only items that contain the query string (as a substring) in at least one of
    the three fields are returned.  Missing publisher or bundle fields are ignored.
    """
    query_lower = query.strip().lower()

    def _matches(item: dict) -> bool:
        return (
            query_lower in item["title"].lower()
            or query_lower in item.get("publisher", "").lower()
            or query_lower in item.get("bundle", "").lower()
        )

    return [item for item in items if _matches(item)]


def format_search_results(matches: list[dict], query: str) -> str:
    """Build a human-readable string of search *matches* for the given *query*.

    Returns a header line with the match count followed by a formatted block for
    each matched item (title, bundle, available formats).
    """
    if not matches:
        return f"[!] No results found for '{query}'."

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Search results for: '{query}' ({len(matches)} match(es))")
    lines.append("-" * 60)

    for item in matches:
        formats = ", ".join(item.get("available_formats", []))
        lines.append(f"  Title:    {item['title']}")
        lines.append(f"  Bundle:   {item.get('bundle', 'Unknown')}")
        lines.append(f"  Formats:  {formats}")
        lines.append("-" * 60)

    return "\n".join(lines)