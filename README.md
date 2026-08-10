# Humble Library Sync

A multi-user FastAPI web application for syncing, cataloging, and analyzing your Humble Bundle purchases. Data is stored in a local SQLite database (`humble_library.db`) via SQLAlchemy ORM, with HTMX-powered partials for a responsive single-page experience.

## Features

- **Library Sync**: Paste your Humble Bundle session cookie to pull your full library into the database via the async API client (`services/client.py`).
- **Library Browser**: Search, filter, and sort your catalog by title, publisher, or bundle. Drill into individual items to view download links and format availability (`routers/library.py`).
- **Deal Inspector**: Evaluate active Humble Bundle deals against your existing library. See overlap percentage, new items, tier breakdowns, and wishlist matches (`routers/deals.py`, `services/evaluator.py`).
- **Expired Deal History**: Track past deal evaluations and revisit expired bundles with saved analysis (`services/deal_logger.py`).
- **Book Log**: Maintain a wishlist and reading tracker with status, notes, target price, and cover art. Exportable as a plain-text manifest (`routers/booklog.py`, `routers/export.py`).
- **Multi-User Support**: Cookie-based JWT authentication via `fastapi-users`. Each user's library, deals, and book log are fully isolated (`humble_sync/auth.py`).
- **Alembic Migrations**: Database schema is managed through Alembic for safe upgrades (`alembic/`).

## Requirements

- Python 3.10+

## Installation

```bash
pip install -e ".[dev]"
```

The SQLite database is created automatically on first run. To apply schema migrations on an existing database:

```bash
alembic upgrade head
```

## Usage

Start the development server:

```bash
uvicorn app.main:app --reload
```

The app is available at [http://127.0.0.1:8000](http://127.0.0.1:8000). Register a new account at `/register`, then log in at `/login`.

### Key Pages

| Route | Description |
| --- | --- |
| `/` | Dashboard with library overview and search |
| `/deals` | Live deal inspector and expired deal history |
| `/booklog` | Wishlist and reading tracker |
| `/library/sync` | Sync your Humble Bundle library via session cookie |

### Health Check

A `GET /health` endpoint returns `{"status": "ok"}` for monitoring and smoke tests.

## Module Architecture

| Module | Purpose |
| --- | --- |
| `app/main.py` | FastAPI application factory, router registration, exception handlers |
| `app/dependencies.py` | Request-scoped FastAPI dependencies (database session injection) |
| `app/routers/dashboard.py` | Root `/` endpoint with item count and user context |
| `app/routers/library.py` | Library search, overview metrics, publisher/bundle lists, item detail |
| `app/routers/deals.py` | Live deal fetching, evaluation, and expired deal history |
| `app/routers/sync.py` | Session-cookie library synchronization endpoints |
| `app/routers/booklog.py` | Book log CRUD (wishlist, reading, notes, target price) |
| `app/routers/export.py` | Plain-text manifest download for book log entries |
| `app/routers/web_auth.py` | HTML login and registration pages |
| `humble_sync/auth.py` | FastAPI-Users config: cookie transport, JWT strategy, user manager |
| `humble_sync/config.py` | Centralized constants (URLs, user-agent, cache TTL) |
| `humble_sync/db/database.py` | SQLAlchemy engine, session factories, `init_db()` |
| `humble_sync/db/models.py` | ORM schemas: `Bundle`, `Item`, `EvaluatedBundle`, `UserBookLog`, `User` |
| `humble_sync/db/queries.py` | Reusable query helpers for all database lookups |
| `humble_sync/utils/text.py` | Title normalization, volume extraction, and fuzzy matching |
| `humble_sync/services/client.py` | Async HTTP client for direct Humble Bundle API sync |
| `humble_sync/services/evaluator.py` | Deal overlap math and tier breakdown formatting |
| `humble_sync/services/deal_logger.py` | Evaluated bundle persistence and expiration tracking |
| `humble_sync/services/bundle_cache.py` | JSON dump file I/O and TTL cache invalidation |
| `humble_sync/services/parser.py` | JSONL parsing engine and database sync layer |
| `humble_sync/services/scraper.py` | Low-level HTTP requests and landing page HTML/JSON parsing |
| `humble_sync/services/status.py` | Catalog health and CDN link validity from SQLite |
| `humble_sync/services/duplicates.py` | Duplicate title detection and cluster analysis |

## Testing

```bash
pytest
```

## License

MIT