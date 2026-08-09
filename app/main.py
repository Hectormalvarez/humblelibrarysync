"""
Main entry point for the Humble Library Sync web GUI.
Uvicorn will look for the `app` object in this module when booting the server.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from humble_sync.auth import auth_backend, fastapi_users, UserRead, UserCreate

from app.routers.dashboard import router as dashboard_router
from app.routers.deals import router as deals_router
from app.routers.library import router as library_router
from app.routers.sync import router as sync_router
from app.routers.web_auth import router as web_auth_router
from app.routers.booklog import router as booklog_router

# Initialize the FastAPI application instance.
# This is the central object that routes HTTP requests to the appropriate handlers.
app = FastAPI(
    title="Humble Library Sync",
    description="Web GUI for managing and exploring your Humble Bundle library.",
    version="0.1.0",
)

# Mount the static files directory so that CSS, JS, and other assets at
# app/static/ are served under the /static URL prefix.
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include the dashboard router which handles the root "/" endpoint.
app.include_router(dashboard_router)

# Include the library router which handles the "/library" endpoints.
app.include_router(library_router)

# Include the deals router which handles the "/deals" endpoints.
app.include_router(deals_router)

# Include the sync router which handles the "/library/sync" endpoints.
app.include_router(sync_router)

# Include the web auth router which handles GET /login and GET /register.
app.include_router(web_auth_router)

# Include the book log router for wishlist/reading items.
app.include_router(booklog_router)

# Include the auth and registration routers from fastapi-users.
app.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/auth/jwt",
    tags=["auth"],
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)


from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Redirect browser requests to /login on 401; return JSON otherwise.

    We intercept Starlette HTTPException with status 401 raised by
    fastapi-users when no valid credentials are provided.
    """
    if exc.status_code == 401:
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    # Re-raise all other HTTP exceptions with the default handler
    from fastapi.exception_handlers import http_exception_handler as _default
    return await _default(request, exc)


@app.get("/health")
def health_check():
    """
    Health-check endpoint.
    Returns a simple JSON payload to confirm the FastAPI application is running
    and reachable. Used by container orchestrators, monitoring tools, and manual
    smoke tests after deployment.
    """
    return {"status": "ok", "message": "GUI active"}
