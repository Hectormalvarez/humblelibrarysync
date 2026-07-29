# Humble Library Sync

A lightweight, local tool to capture, parse, and catalog your Humble Bundle library data via automated browser inspection and local JSON processing.

## How to Use

1. **Install dependencies:**

```bash
   pip install -r requirements.txt
   playwright install chromium

```

1. **Capture library data:**

```bash
python capture.py

```

*(Log in manually on first run if prompted, then scroll through your library page until all items load).*
3. **Parse and extract structured catalog:**

```bash
python parse.py

```

## User Flows

* **Capture Flow (`capture.py`):** Launches an automated browser session, bypasses logins using saved credentials, refreshes the page to bypass local caching, and intercepts background API payloads to generate `raw_library_dump.json`.
* **Parsing Flow (`parse.py`):** Reads the raw capture data, filters out promotions and coupons, normalizes metadata across standard products and third-party keys, extracts download links and link expiration timestamps, and outputs clean `my_library.txt`, `my_library.json`, and `my_library.csv` catalog files.
