"""
Duplicate cross-reference engine for Humble Library Sync.
Identifies titles that appear across multiple bundle purchases.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def normalize_title(title: str) -> str:
    """Lowercases, strips punctuation, and collapses whitespace for fuzzy matching."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def find_duplicates(items: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    """
    Pure analysis engine: Scans items and returns duplicate clusters 
    grouped by normalized title.
    """
    grouped_titles: dict[str, list[dict[str, str]]] = {}

    for item in items:
        raw_title = item.get("title", "").strip()
        bundle = item.get("bundle", "Unknown Bundle")
        purchase_date = item.get("purchase_date", "Unknown Date")

        if not raw_title:
            continue

        norm_title = normalize_title(raw_title)

        if norm_title not in grouped_titles:
            grouped_titles[norm_title] = []

        grouped_titles[norm_title].append({
            "display_title": raw_title,
            "bundle": bundle,
            "purchase_date": purchase_date,
        })

    # Return only entries that appear in more than one bundle
    return {
        norm: entries 
        for norm, entries in grouped_titles.items() 
        if len(entries) > 1
    }


def format_duplicate_report(
    duplicates: dict[str, list[dict[str, str]]], 
    total_items: int = 0, 
    source_file: str = "my_library.json"
) -> str:
    """Formats raw duplicate data into a plain text report for terminal output."""
    unique_bundles = {
        entry["bundle"] 
        for entries in duplicates.values() 
        for entry in entries
    }

    lines = [
        "=" * 50,
        "LIBRARY DUPLICATE REPORT",
        "=" * 50,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Data source: {source_file}",
        "-" * 50,
        "OVERVIEW",
        f"  Total items scanned:  {total_items}",
        f"  Duplicate clusters:   {len(duplicates)} titles",
        f"  Bundles involved:     {len(unique_bundles)}",
        "-" * 50,
        "DUPLICATES",
        "-" * 50,
    ]

    if not duplicates:
        lines.append("No duplicates found across your bundles.")
    else:
        for norm_title in sorted(duplicates.keys()):
            entries = duplicates[norm_title]
            display_title = entries[0]["display_title"]
            lines.append(f'"{display_title}"')
            for entry in entries:
                lines.append(f"  - {entry['bundle']} ({entry['purchase_date']})")
            lines.append("")

    lines.append("=" * 50)
    return "\n".join(lines)


def load_library(filepath: str | Path) -> tuple[list[dict], dict[str, Any]]:
    """Loads and returns items list and metadata from a parsed library JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Library file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    return catalog.get("items", []), catalog.get("metadata", {})


if __name__ == "__main__":
    target = Path("my_library.json")
    if target.exists():
        items, meta = load_library(target)
        duplicates = find_duplicates(items)
        report = format_duplicate_report(
            duplicates=duplicates, 
            total_items=len(items), 
            source_file=str(target)
        )
        print(report)