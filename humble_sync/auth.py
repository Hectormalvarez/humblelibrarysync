"""FastAPI-Users authentication components.

Configures cookie-based transport, JWT strategy, the async user-manager, and
the request-scoped DB / manager dependencies consumed by FastAPI routers.
"""

import uuid
from typing import Optional

from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from humble_sync.db.database import AsyncSessionLocal
from humble_sync.db.models import User

COOKIE_NAME = "humble_auth"
COOKIE_MAX_AGE = 86400 * 7  # 7 days in seconds

SECRET_KEY = "CHANGEME_SECRET_KEY_FOR_DEV"


# ---------------------------------------------------------------------------
# Transport & strategy
# ---------------------------------------------------------------------------

cookie_transport = CookieTransport(
    cookie_name=COOKIE_NAME,
    cookie_max_age=COOKIE_MAX_AGE,
)


def get_jwt_strategy() -> JWTStrategy:
    """Return a JWT strategy with a configurable secret and lifetime."""
    return JWTStrategy(
        secret=SECRET_KEY,
        lifetime_seconds=COOKIE_MAX_AGE,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)


# ---------------------------------------------------------------------------
# User manager
# ---------------------------------------------------------------------------

class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Application-specific user manager with basic lifecycle hooks."""

    reset_password_token_secret = SECRET_KEY
    verification_token_secret = SECRET_KEY

    async def on_after_register(
        self, user: User, request: Optional[object] = None
    ) -> None:
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[object] = None
    ) -> None:
        print(
            f"User {user.id} has forgotten their password. "
            f"Reset token: {token}"
        )

    async def on_after_request_verification(
        self, user: User, token: str, request: Optional[object] = None
    ) -> None:
        print(
            f"Verification requested for user {user.id}. "
            f"Verification token: {token}"
        )


# ---------------------------------------------------------------------------
# Async dependency helpers
# ---------------------------------------------------------------------------

async def get_user_db():
    """Yield a ``SQLAlchemyUserDatabase`` backed by an async session."""
    async with AsyncSessionLocal() as session:
        yield SQLAlchemyUserDatabase(session, User)  # type: ignore[arg-type]


async def get_user_manager():
    """Yield a ``UserManager`` backed by the async user DB dependency."""
    yield UserManager(get_user_db())  # type: ignore[arg-type]