# Humble Library Sync

A modular Python toolkit to capture, parse, analyze, and track your Humble Bundle purchases and direct CDN download links.

## Features

- **Interactive CLI Dashboard**: Launch `cli.py` for an arrow-key driven menu to check catalog health, run syncs, and analyze duplicates.
- **Passive API Interception**: Uses Playwright to capture API responses directly from Humble Bundle without fragile web scrapers (`capture.py`).
- **Catalog Parser & Exporter**: Normalizes raw JSONL dumps into clean JSON, CSV, and TXT files with detailed metadata (`parse.py`).
- **Duplicate Cross-Referencer**: Scans catalog for titles appearing across multiple bundle purchases (`library_duplicates.py`).
- **CDN Link Health Tracking**: Calculates sync age and tracks HMAC signature expiration on download URLs (`status.py`).

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
playwright install chromium

```

## Usage

### Interactive Mode

Run the CLI without arguments to launch the interactive menu:

```bash
python cli.py

```

### Subcommand Mode

Run individual commands directly for scripting or automated pipelines:

```bash
# View catalog status and link expiration
python cli.py status

# Run browser network capture
python cli.py capture

# Parse raw dump into JSON/CSV/TXT
python cli.py parse

# Check for duplicate titles across purchases
python cli.py duplicates

```

## Module Architecture

| Module | Purpose |
| --- | --- |
| `cli.py` | Unified entrypoint providing interactive menu and subcommand routing |
| `status.py` | Calculates catalog metrics, sync age, and CDN link validity |
| `parse.py` | Pure parsing engine transforming JSONL dumps to normalized catalog formats |
| `library_duplicates.py` | Title normalization and duplicate cluster identification |
| `capture.py` | Playwright network listener intercepting API payloads |
