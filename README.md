# Humble Library Sync

A modular Python toolkit to capture, parse, persist, and analyze your Humble Bundle purchases. Catalog data and deal evaluations are stored in a local SQLite database (`humble_library.db`) via SQLAlchemy ORM, with optional JSON/CSV/TXT exports.

## Features

- **Database Sync & Ingestion**: Parses JSONL API captures and bulk-syncs normalized records (`Bundle` and `Item`) into SQLite (`parse.py` & `database.py`).
- **Interactive CLI Dashboard**: Runs terminal menu loops for search, status, duplicate analysis, and deal evaluation backed by SQLite (`cli.py`).
- **Live Deal Evaluator**: Evaluates active bundles against owned items in the database and tracks deal history in the `evaluated_bundles` table (`bundle_inspector.py`).
- **CDN Link Health & Duplicate Tracking**: Queries SQL for active vs expired download links and title clusters (`status.py`, `library_duplicates.py`).
- **Passive API Interception**: Uses Playwright to capture API responses directly from Humble Bundle without fragile web scrapers (`capture.py`).

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
playwright install chromium

```

The database (`humble_library.db`) is initialized automatically on first run.

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

# Parse raw dump and sync to the database (supports --json-out, --csv-out, --txt-out for exports)
python cli.py parse

# Check for duplicate titles across purchases
python cli.py duplicates

# Evaluate live bundles against owned inventory
python cli.py inspect

```

## Module Architecture

| Module | Purpose |
| --- | --- |
| `database.py` | Engine initialization, session management, and `DATABASE_URL` setup |
| `models.py` | SQLAlchemy ORM schemas (`Bundle`, `Item`, `EvaluatedBundle`) |
| `cli.py` | Unified entrypoint, database state onboarding, and interactive menu routing |
| `parse.py` | JSONL parsing engine and database sync layer (`sync_catalog_to_db`) |
| `status.py` | Calculates catalog health and CDN link validity directly from SQLite |
| `bundle_inspector.py` | Evaluates live deals and persists snapshots in `evaluated_bundles` table |
| `library_duplicates.py` | Duplicate title detection and cluster analysis via database queries |
| `search.py` | Preloads unique titles from SQLite for fast interactive `prompt_toolkit` autocomplete |
| `capture.py` | Playwright network listener intercepting raw Humble API payloads |
