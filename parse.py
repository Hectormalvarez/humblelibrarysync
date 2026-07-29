import json
import csv
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

DUMP_FILE = "raw_library_dump.json"
TXT_OUTPUT = "my_library.txt"
JSON_OUTPUT = "my_library.json"
CSV_OUTPUT = "my_library.csv"

def extract_expiration_from_url(url_string):
    """
    Parses Humble Bundle's HMAC signature query string to extract 
    the UNIX expiration timestamp ('exp=').
    """
    if not url_string:
        return None
    try:
        parsed_url = urlparse(url_string)
        query_params = parse_qs(parsed_url.query)
        
        # Humble Bundle passes signatures like 'st=1785...~exp=1785436579~hmac=...'
        t_param = query_params.get("t", [""])[0]
        for part in t_param.split("~"):
            if part.startswith("exp="):
                exp_epoch = int(part.split("=")[1])
                return datetime.fromtimestamp(exp_epoch, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return None

def parse_library():
    """
    Parses intercepted Humble Bundle API payloads and enriches product metadata
    with direct download URLs, file sizes, MD5 hashes, and link expiration timestamps.
    """
    if not os.path.exists(DUMP_FILE):
        print(f"[!] Error: {DUMP_FILE} not found. Run capture.py first.")
        return

    # Record when the raw capture dump file was generated/modified
    dump_mtime = os.path.getmtime(DUMP_FILE)
    captured_at = datetime.fromtimestamp(dump_mtime, tz=timezone.utc).isoformat()

    library = {}

    with open(DUMP_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
                if isinstance(payload, str):
                    payload = json.loads(payload)

                if not isinstance(payload, dict):
                    continue

                data = payload.get("data", {})

                for bundle_key, bundle in data.items():
                    if not isinstance(bundle, dict):
                        continue

                    bundle_title = bundle.get("product", {}).get("human_name", "")
                    purchase_date = bundle.get("created", "")

                    # 1. Process Standard Subproducts (Books, Software, Downloads)
                    for sub in bundle.get("subproducts", []):
                        title = sub.get("human_name", "").strip()
                        if not title or "Discount" in title or "Coupon" in title:
                            continue

                        downloads_map = {}
                        
                        for download in sub.get("downloads", []):
                            for struct in download.get("download_struct", []):
                                fmt = struct.get("name")
                                web_url = struct.get("url", {}).get("web", "")
                                
                                if fmt and web_url:
                                    fmt_key = fmt.upper()
                                    expires_at = extract_expiration_from_url(web_url)
                                    
                                    downloads_map[fmt_key] = {
                                        "url": web_url,
                                        "file_size_bytes": struct.get("file_size"),
                                        "human_size": struct.get("human_size", ""),
                                        "md5": struct.get("md5", ""),
                                        "sha1": struct.get("sha1", ""),
                                        "url_expires_at": expires_at
                                    }

                        publisher = sub.get("payee", {}).get("human_name", "Unknown")

                        key = (title, bundle_title)
                        if key not in library:
                            library[key] = {
                                "title": title,
                                "publisher": publisher,
                                "bundle": bundle_title,
                                "purchase_date": purchase_date,
                                "captured_at": captured_at,
                                "available_formats": sorted(list(downloads_map.keys())),
                                "downloads": downloads_map,
                                "type": "download"
                            }

                    # 2. Process Third-Party Keys (Zenva, Pluralsight, Software Keys)
                    tpk_dict = bundle.get("tpkd_dict", {})
                    for tpk in tpk_dict.get("all_tpks", []):
                        title = tpk.get("human_name", "").strip()
                        if not title:
                            continue

                        platform = tpk.get("key_type_human_name", "Third-Party Key")

                        key = (title, bundle_title)
                        if key not in library:
                            library[key] = {
                                "title": title,
                                "publisher": platform,
                                "bundle": bundle_title,
                                "purchase_date": purchase_date,
                                "captured_at": captured_at,
                                "available_formats": ["KEY"],
                                "downloads": {},
                                "type": "redemption_key"
                            }

            except (json.JSONDecodeError, AttributeError):
                continue

    sorted_library = sorted(library.values(), key=lambda x: (x["title"].lower(), x["bundle"].lower()))

    # --- Export 1: Plain Text (Titles only) ---
    with open(TXT_OUTPUT, "w", encoding="utf-8") as f:
        for item in sorted_library:
            f.write(f"{item['title']}\n")

    # --- Export 2: Enriched JSON Catalog ---
    catalog = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dump_captured_at": captured_at,
            "total_items": len(sorted_library)
        },
        "items": sorted_library
    }
    
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2)

    # --- Export 3: CSV Summary ---
    with open(CSV_OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["title", "publisher", "bundle", "purchase_date", "captured_at", "available_formats", "type"])
        writer.writeheader()
        for item in sorted_library:
            row = {
                "title": item["title"],
                "publisher": item["publisher"],
                "bundle": item["bundle"],
                "purchase_date": item["purchase_date"],
                "captured_at": item["captured_at"],
                "available_formats": ", ".join(item["available_formats"]),
                "type": item["type"]
            }
            writer.writerow(row)

    print(f"[*] Parsing complete!")
    print(f"    - Total items cataloged: {len(sorted_library)}")
    print(f"    - Capture Timestamp: {captured_at}")
    print(f"    - Catalog exported to: {JSON_OUTPUT}")

if __name__ == "__main__":
    parse_library()