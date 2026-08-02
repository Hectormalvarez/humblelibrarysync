---
paths:
  - "*.py"
  - "app/**/*.py"
  - "tests/**/*.py"
---
# Python, FastAPI & SQLAlchemy Standards

## Database & ORM Patterns
- Use SQLAlchemy 2.0+ Declarative Base and mapped columns (`Mapped`, `mapped_column`) as established in `models.py`.
- Always use request-scoped session injection via `Depends(get_db)` in FastAPI routers to ensure safe transaction rollbacks and commits.
- Ensure SQLite compatibility: avoid backend-specific JSON functions when handling JSON columns (e.g., parse/aggregate JSON arrays in Python if necessary, as seen in `library_overview`).

## Scraping & Parsing Logic
- Keep network operations (`capture.py`, `bundle_inspector.py`) completely decoupled from database persistence layers (`parse.py`, `database.py`).
- Implement robust error handling (`requests.RequestException`, `JSONDecodeError`) with fallback mechanisms for stale cache states.