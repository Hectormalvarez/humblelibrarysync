"""
Core parsing engine for Humble Bundle API dumps.
Transforms raw JSONL payloads into normalized in-memory catalog structures.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from humble_sync.db.database import SessionLocal, init_db
from humble_sync.db.models import Bundle, Item


def extract_expiration_from_url(url_string: str) -> Optional[str]:
    """Extracts the 'exp=' UNIX expiration timestamp from Humble's signed URL string."""
    if not url_string:
        return None
    try:
        query_params = parse_qs(urlparse(url_string).query)
        t_param = query_params.get("t", [""])[0]

        for part in t_param.split("~"):
            if part.startswith("exp="):
                epoch = int(part.split("=")[1])
                return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (ValueError, IndexError, AttributeError):
        pass
    return None


def extract_downloads(subproduct: dict) -> dict[str, dict]:
    """Parses available download formats (PDF, EPUB, MOBI) for a single product."""
    downloads_map = {}

    for download in subproduct.get("downloads", []):
        for struct in download.get("download_struct", []):
            fmt = struct.get("name")
            web_url = struct.get("url", {}).get("web", "")

            if fmt and web_url:
                downloads_map[fmt.upper()] = {
                    "url": web_url,
                    "file_size_bytes": struct.get("file_size"),
                    "human_size": struct.get("human_size", ""),
                    "md5": struct.get("md5", ""),
                    "sha1": struct.get("sha1", ""),
                    "url_expires_at": extract_expiration_from_url(web_url),
                }

    return downloads_map


def extract_items_from_bundle(bundle: dict, captured_at: str) -> list[dict]:
    """Extracts books, software downloads, and redemption keys from a bundle payload."""
    items = []
    bundle_title = bundle.get("product", {}).get("human_name", "")
    purchase_date = bundle.get("created", "")

    # 1. Standard Downloads (Books, Audiobooks, Software)
    for sub in bundle.get("subproducts", []):
        title = sub.get("human_name", "").strip()
        if not title or "Discount" in title or "Coupon" in title:
            continue

        downloads_map = extract_downloads(sub)
        publisher = sub.get("payee", {}).get("human_name", "Unknown")

        items.append({
            "title": title,
            "publisher": publisher,
            "bundle": bundle_title,
            "purchase_date": purchase_date,
            "captured_at": captured_at,
            "available_formats": sorted(downloads_map.keys()),
            "downloads": downloads_map,
            "type": "download",
        })

    # 2. Third-Party Keys
    tpk_dict = bundle.get("tpkd_dict", {})
    for tpk in tpk_dict.get("all_tpks", []):
        title = tpk.get("human_name", "").strip()
        if title:
            items.append({
                "title": title,
                "publisher": tpk.get("key_type_human_name", "Third-Party Key"),
                "bundle": bundle_title,
                "purchase_date": purchase_date,
                "captured_at": captured_at,
                "available_formats": ["KEY"],
                "downloads": {},
                "type": "redemption_key",
            })

    return items


def parse_dump(dump_file: str | Path) -> dict[str, Any]:
    """
    Parses a raw JSONL dump into a structured in-memory catalog dictionary.
    Pure data transformation: No disk writes or side effects.
    """
    dump_path = Path(dump_file)
    if not dump_path.exists():
        raise FileNotFoundError(f"Dump file not found: {dump_path}")

    dump_mtime = dump_path.stat().st_mtime
    captured_at = datetime.fromtimestamp(dump_mtime, tz=timezone.utc).isoformat()

    catalog_map: dict[tuple[str, str], dict] = {}

    with open(dump_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                payload = json.loads(line)
                if isinstance(payload, str):
                    payload = json.loads(payload)

                data = payload.get("data", {})
                for bundle in data.values():
                    if not isinstance(bundle, dict):
                        continue

                    for item in extract_items_from_bundle(bundle, captured_at):
                        key = (item["title"], item["bundle"])
                        if key not in catalog_map:
                            catalog_map[key] = item

            except (json.JSONDecodeError, AttributeError):
                continue

    sorted_items = sorted(
        catalog_map.values(), 
        key=lambda x: (x["title"].lower(), x["bundle"].lower())
    )

    return {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dump_captured_at": captured_at,
            "total_items": len(sorted_items),
        },
        "items": sorted_items,
    }


def export_to_json(catalog: dict[str, Any], output_file: str | Path) -> None:
    """Exports structured catalog data to a formatted JSON file."""
    output_path = Path(output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)


def export_to_csv(catalog: dict[str, Any], output_file: str | Path) -> None:
    """Exports catalog summary to a CSV file."""
    output_path = Path(output_file)
    items = catalog.get("items", [])
    fieldnames = ["title", "publisher", "bundle", "purchase_date", "captured_at", "available_formats", "type"]

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            row = item.copy()
            row["available_formats"] = ", ".join(item["available_formats"])
            row.pop("downloads", None)
            writer.writerow(row)


def export_to_txt(catalog: dict[str, Any], output_file: str | Path) -> None:
    """Exports a simple newline-delimited list of titles to a text file."""
    output_path = Path(output_file)
    items = catalog.get("items", [])
    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(f"{item['title']}\n")


def sync_catalog_to_db(catalog_data: dict[str, Any]) -> None:
    """Syncs parsed catalog data into the database using upsert logic for idempotency.

    This function can be safely re-run without creating duplicates:
    - Existing bundles are matched by title
    - Existing items are matched by (bundle_id, title) combination
    - If a match is found, the record is updated; otherwise, a new record is created
    """
    init_db()
    db = SessionLocal()
    try:
        bundles_by_title: dict[str, list[dict]] = {}
        for item in catalog_data["items"]:
            bundle_title = item["bundle"]
            bundles_by_title.setdefault(bundle_title, []).append(item)

        for bundle_title, items in bundles_by_title.items():
            # Upsert bundle: check if bundle with this title already exists
            bundle = db.query(Bundle).filter_by(title=bundle_title).first()
            if bundle:
                # Update existing bundle metadata
                bundle.purchase_date = items[0].get("purchase_date")
                bundle.captured_at = items[0].get("captured_at")
            else:
                # Create new bundle
                bundle = Bundle(
                    title=bundle_title,
                    purchase_date=items[0].get("purchase_date"),
                    captured_at=items[0].get("captured_at"),
                )
                db.add(bundle)
                db.flush()  # Get the bundle.id for item association

            for item_data in items:
                # Upsert item: check if item with this title already exists in this bundle
                existing_item = db.query(Item).filter_by(
                    bundle_id=bundle.id,
                    title=item_data["title"]
                ).first()

                if existing_item:
                    # Update existing item
                    existing_item.publisher = item_data.get("publisher", "Unknown")
                    existing_item.item_type = item_data.get("type", "download")
                    existing_item.available_formats = item_data.get("available_formats", [])
                    existing_item.downloads = item_data.get("downloads", {})
                else:
                    # Create new item
                    new_item = Item(
                        title=item_data["title"],
                        publisher=item_data.get("publisher", "Unknown"),
                        item_type=item_data.get("type", "download"),
                        available_formats=item_data.get("available_formats", []),
                        downloads=item_data.get("downloads", {}),
                    )
                    bundle.items.append(new_item)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dump = Path("raw_library_dump.json")
    if dump.exists():
        data = parse_dump(dump)
        export_to_json(data, "my_library.json")
        export_to_csv(data, "my_library.csv")
        export_to_txt(data, "my_library.txt")
        print(f"[*] Parsed {data['metadata']['total_items']} items into JSON, CSV, and TXT.")