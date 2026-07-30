"""
Main entry point for the Humble Library Sync web GUI.
Uvicorn will look for the `app` object in this module when booting the server.
"""

from fastapi import FastAPI

# Initialize the FastAPI application instance.
# This is the central object that routes HTTP requests to the appropriate handlers.
app = FastAPI(
    title="Humble Library Sync",
    description="Web GUI for managing and exploring your Humble Bundle library.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """
    Health-check endpoint.
    Returns a simple JSON payload to confirm the FastAPI application is running
    and reachable. Used by container orchestrators, monitoring tools, and manual
    smoke tests after deployment.
    """
    return {"status": "ok", "message": "GUI active"}