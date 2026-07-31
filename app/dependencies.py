"""
Centralized FastAPI dependencies for request-scoped injection.

This module consolidates all dependency functions used across the application's
routers, making it easy to override the database in future tests without
refactoring core logic.
"""

from database import get_db