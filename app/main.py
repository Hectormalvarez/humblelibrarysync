"""
Main entry point for the Humble Library Sync web GUI.
Uvicorn will look for the `app` object in this module when booting the server.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.routers.dashboard import router as dashboard_router
from app.routers.library import router as library_router

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


@app.get("/health")
def health_check():
    """
    Health-check endpoint.
    Returns a simple JSON payload to confirm the FastAPI application is running
    and reachable. Used by container orchestrators, monitoring tools, and manual
    smoke tests after deployment.
    """
    return {"status": "ok", "message": "GUI active"}
