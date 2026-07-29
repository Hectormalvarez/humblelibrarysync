#!/usr/bin/env python3
"""
Library Duplicate Report Generator for Humble Library Sync
Reads my_library.json and lists titles that appear in multiple bundles.
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_INPUT = "my_library.json"


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation except alphanumerics, and collapse whitespace."""
    title = title.lower()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def load_library(filepath: str):
    """Load and return the items list from a library JSON file."""
    if not os.path.exists(filepath):
        print(f"[!] Error: {filepath} not found.")
        return None, None

    with open(filepath, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    items = catalog.get("items", [])
    metadata = catalog.get("metadata", {})
    return items, metadata


def generate_report(items: list) -> str:
    """Build a report showing titles that appear in more than one bundle."""
    if not items:
        return "No items in library."

    exact_groups = defaultdict(list)
    all_titles = set()
    bundle_set = set()

    for item in items:
        title = item.get("title", "").strip()
        bundle = item.get("bundle", "Unknown Bundle")
        purchase = item.get("purchase_date", "Unknown Date")
        norm_title = normalize_title(title)
        exact_groups[norm_title].append((title, bundle, purchase))
        all_titles.add(norm_title)
        bundle_set.add(bundle)

    duplicates = {
        nt: entries
        for nt, entries in exact_groups.items()
        if len(entries) > 1
    }

    report_lines = []
    report_lines.append("=" * 50)
    report_lines.append("LIBRARY DUPLICATE REPORT")
    report_lines.append("=" * 50)
    report_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    report_lines.append(f"Data source: {DEFAULT_INPUT}")
    report_lines.append("-" * 50)
    report_lines.append("OVERVIEW")
    report_lines.append(f"  Total items:          {len(items)}")
    report_lines.append(f"  Unique titles:        {len(all_titles)}")
    report_lines.append(f"  Bundles represented:  {len(bundle_set)}")
    report_lines.append(f"  Duplicate clusters:   {len(duplicates)} titles in multiple bundles")
    report_lines.append("")

    report_lines.append("-" * 50)
    report_lines.append("DUPLICATES")
    report_lines.append("-" * 50)
    if not duplicates:
        report_lines.append("None found.")
    else:
        for norm_title in sorted(duplicates.keys()):
            occurrences = duplicates[norm_title]
            display_title = occurrences[0][0]
            report_lines.append(f'"{display_title}"')
            for _, bundle, purchase in occurrences:
                report_lines.append(f"  - {bundle} ({purchase})")
            report_lines.append("")

    report_lines.append("=" * 50)
    return "\n".join(report_lines)


def main():
    items, metadata = load_library(DEFAULT_INPUT)
    if items is None:
        return
    report = generate_report(items)
    return report


if __name__ == "__main__":
    print(main())