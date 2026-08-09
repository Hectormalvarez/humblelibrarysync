"""
Web auth router – serves GET /login and GET /register HTML views.
"""

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_page(request: Request):
    """Render the login form page."""
    return templates.TemplateResponse(request, "pages/login.html")


@router.get("/register")
def register_page(request: Request):
    """Render the registration form page."""
    return templates.TemplateResponse(request, "pages/register.html")