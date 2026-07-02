"""FastAPI entry point for the Expert System for Critical Asset Management.

This module initializes the web application, configures authentication,
sets up Jinja2 templating, and defines all HTML page routes.

The simulation background task is started during application startup
via the lifespan context manager.
"""

import os
import asyncio
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import Environment, FileSystemLoader

from web.api import router as api_router, run_simulation
from core.knowledge_base import KnowledgeBase
from storage.database import init_db
from scripts.seed import seed

BASE_DIR = Path(__file__).parent
kb = KnowledgeBase()


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, seed data, and start the simulation loop on startup.
    Cancels the simulation task on shutdown."""
    init_db()
    seed()
    task = asyncio.create_task(run_simulation())
    yield
    task.cancel()


app = FastAPI(title="Sistema Experto - Gestión de Activos Críticos", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api_router)

jinja_env = Environment(loader=FileSystemLoader(str(BASE_DIR / "web" / "templates")))

PROTECTED_PATHS = {"/", "/config", "/sensor-input", "/map", "/asset", "/admin", "/reports"}
ADMIN_PATHS = {"/config", "/admin"}


async def require_auth(request: Request):
    """Check if the user is authenticated. Returns a RedirectResponse if not."""
    if request.url.path not in PROTECTED_PATHS:
        return None
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    role = request.session.get("role", "")
    path = request.url.path
    if path in ADMIN_PATHS and role != "admin":
        return RedirectResponse(url="/", status_code=303)
    return None


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware that protects page routes behind authentication."""
    redirect = await require_auth(request)
    if redirect:
        return redirect
    return await call_next(request)


SECRET_KEY = os.environ.get("SECRET_KEY", "capstone-secret-key-2026")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    """Render the login page. Redirects to dashboard if already authenticated."""
    if request.session.get("user"):
        return RedirectResponse(url="/", status_code=303)
    template = jinja_env.get_template("login.html")
    return HTMLResponse(template.render({"error": error}))


@app.post("/login")
async def login_post(request: Request):
    """Handle login form submission. Validates credentials against the DB User model."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = kb.get_user(username)
    if user and user.password_hash == _hash(password):
        request.session["user"] = username
        request.session["role"] = user.role
        request.session["condominium_id"] = user.condominium_id
        kb.add_audit(username, "login", "Inicio de sesión", user_id=user.id)
        return RedirectResponse(url="/", status_code=303)
    template = jinja_env.get_template("login.html")
    return HTMLResponse(template.render({"error": "Usuario o contraseña incorrectos"}))


@app.get("/logout")
async def logout(request: Request):
    """Clear the session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main monitoring dashboard."""
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Render the configuration page (rules, sensors, membership functions)."""
    template = jinja_env.get_template("config.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/sensor-input", response_class=HTMLResponse)
async def sensor_input_page(request: Request):
    """Render the mobile sensor input page for manual/phone sensor data."""
    template = jinja_env.get_template("sensor_input.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/map", response_class=HTMLResponse)
async def map_page(request: Request):
    """Render the georeferenced map showing condominium locations with asset status."""
    template = jinja_env.get_template("map.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/asset", response_class=HTMLResponse)
async def asset_page(request: Request, id: int = 0):
    """Render the asset technical sheet with detailed information."""
    asset = kb.get_asset(id) if id else None
    template = jinja_env.get_template("asset.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "asset_id": id,
        "asset": asset,
    }))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Render the admin panel for user management, audit logs, and hierarchy."""
    template = jinja_env.get_template("admin.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request):
    """Render the reports page with filters and download options."""
    template = jinja_env.get_template("reports.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
