# Humble Library Sync

A modular Python toolkit to capture, parse, persist, and analyze your Humble Bundle purchases. Catalog data and deal evaluations are stored in a local SQLite database (`humble_library.db`) via SQLAlchemy ORM, with optional JSON/CSV/TXT exports.

## Features

- **Database Sync & Ingestion**: Parses JSONL API captures and bulk-syncs normalized records (`Bundle` and `Item`) into SQLite (`services/parser.py` & `db/database.py`).
- **Web Dashboard**: FastAPI-powered HTML interface with HTMX partials for search, status, duplicate analysis, and deal evaluation (`app/routers/`).
- **Live Deal Evaluator**: Evaluates active bundles against owned items in the database and tracks deal history in the `evaluated_bundles` table (`services/evaluator.py` & `services/deal_logger.py`).
- **CDN Link Health & Duplicate Tracking**: Queries SQL for active vs expired download links and title clusters (`services/status.py`, `services/duplicates.py`).
- **API Synchronization**: Async HTTP client for direct Humble Bundle API synchronization (`services/client.py`).

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
| `config.py` | Centralized application settings, paths, and URLs |
| `db/database.py` | Engine initialization, session management, and `DATABASE_URL` setup |
| `db/queries.py` | Reusable query helpers for database lookups |
| `db/models.py` | SQLAlchemy ORM schemas (`Bundle`, `Item`, `EvaluatedBundle`) |
| `services/scraper.py` | Low-level HTTP requests and landing page HTML/JSON parsing |
| `services/bundle_cache.py` | JSON dump file I/O and TTL cache invalidation |
| `services/deal_logger.py` | Evaluated bundle database persistence and expiration tracking |
| `services/parser.py` | JSONL parsing engine and database sync layer (`sync_catalog_to_db`) |
| `services/evaluator.py` | Pure domain overlap math and report formatting |
| `services/client.py` | Async HTTP client for direct Humble Bundle API synchronization |
| `services/status.py` | Calculates catalog health and CDN link validity directly from SQLite |
| `services/duplicates.py` | Duplicate title detection and cluster analysis via database queries |
