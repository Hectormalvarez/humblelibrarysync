"""
Main entry point for the Humble Library Sync web GUI.
Uvicorn will look for the `app` object in this module when booting the server.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

# Set up Jinja2 template rendering. The templates directory lives under
# app/templates/ and contains the HTML shell plus page-specific templates.
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
def home(request: Request):
    """
    Root endpoint – renders the main web GUI page.
    Uses the Jinja2 template engine to serve the HTML shell defined in
    app/templates/pages/home.html, which extends the base layout.
    """
    return templates.TemplateResponse(request, "pages/home.html")


@app.get("/health")
def health_check():
    """
    Health-check endpoint.
    Returns a simple JSON payload to confirm the FastAPI application is running
    and reachable. Used by container orchestrators, monitoring tools, and manual
    smoke tests after deployment.
    """
    return {"status": "ok", "message": "GUI active"}
