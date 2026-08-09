"""
Centralized FastAPI dependencies for request-scoped injection.

This module consolidates all dependency functions used across the application's
routers, making it easy to override the database in future tests without
refactoring core logic.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from humble_sync.db.database import AsyncSessionLocal, get_db


async def async_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
