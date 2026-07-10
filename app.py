"""FastAPI entry point for the Expert System for Critical Asset Management.

This module initializes the web application, configures authentication,
sets up Jinja2 templating, and defines all HTML page routes.

The simulation background task is started during application startup
via the lifespan context manager.
"""

import os
import asyncio
import hashlib
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from jinja2 import Environment, FileSystemLoader

from web.api import router as api_router
from core.knowledge_base import KnowledgeBase
from storage.database import init_db
from scripts.seed import seed

BASE_DIR = Path(__file__).parent
kb = KnowledgeBase()


def _hash(pw: str) -> str:
    """Hash password with PBKDF2-SHA256 and a random 16-byte salt.
    Returns salt$hash (both hex-encoded) for storage."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


def _verify_password(pw: str, stored: str) -> bool:
    """Verify a password against a salt$hash string."""
    try:
        salt, expected = stored.split("$", 1)
        h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000)
        return h.hex() == expected
    except (ValueError, AttributeError):
        return False





_sim_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, seed data, and start the auto-simulation background task.
    Simulation generates continuous telemetry for all assets unless manual
    data overrides specific sensors. Inference runs on every simulation cycle."""
    global _sim_task
    init_db()
    from web.push_notify import init_vapid
    init_vapid()
    seed()
    # ── Update coordinates for existing DB (from real GPS data) ──
    try:
        from storage.database import get_session
        from models.models import Condominium
        session = get_session()
        for c in session.query(Condominium).all():
            if c.name == "Centro Residencial San Miguel" and (c.lat, c.lng) != (9.7997, -63.1627):
                c.lat, c.lng = 9.7997, -63.1627
            elif c.name == "Condominio Golf Plaza":
                c.lat, c.lng = 9.8001, -63.1614
            elif c.name == "Condominio Vista Golf":
                c.lat, c.lng = 9.8009, -63.1604
            elif c.name == "Condominio San Andrés":
                c.lat, c.lng = 9.7985, -63.1595
            elif c.name == "Condominio La Ceiba":
                c.lat, c.lng = 9.797, -63.163
            elif c.name == "Condominio Villas Merey":
                c.lat, c.lng = 9.798, -63.162
            elif c.name == "Cond. Los Chaguaramos":
                c.lat, c.lng = 9.796, -63.161
            elif c.name == "Condominio Los Robles":
                c.lat, c.lng = 9.797, -63.160
        session.commit(); session.close()
        print("Coordinates updated.")
    except Exception as e:
        print("Coord update skipped:", e)
    # Seed historical readings for demo purposes
    from scripts.seed_readings import seed_readings
    try:
        seed_readings()
    except Exception:
        pass
    from web.api import load_asset_instances, run_simulation, _ensure_asset_caches, _evaluate_asset, latest_sensor_values, history_cache, event_cache, latest_results
    load_asset_instances()
    # Force-initialize all assets with midpoint values so dashboard shows data immediately
    for asset in kb.get_all_assets():
        try:
            _ensure_asset_caches(asset.name, asset.label)
            sensors = kb.get_sensors(asset.id)
            sv = {s.name: (s.min_val + s.max_val) / 2.0 for s in sensors}
            latest_sensor_values[asset.name] = sv
            _evaluate_asset(asset.name, persist_readings=False)
            # Create initial status event after first evaluation
            lr_result = latest_results.get(asset.name, {})
            if lr_result.get("status"):
                event_cache.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "asset": asset.name,
                    "asset_name": asset.label,
                    "from": "inicio",
                    "to": lr_result["status"],
                    "score": lr_result.get("score", 0),
                    "type": "info",
                })
        except Exception:
            pass
    # Load historical readings from DB into history_cache
    for asset in kb.get_all_assets():
        try:
            batches = kb.get_reading_batches(asset.id, limit=20)
            if batches and asset.name not in history_cache:
                history_cache[asset.name] = batches
        except Exception:
            pass
    _sim_task = asyncio.create_task(run_simulation())
    yield
    if _sim_task:
        _sim_task.cancel()
        try:
            await _sim_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Sistema Experto - Gestión de Activos Críticos", lifespan=lifespan)

from web.limits import limiter
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(api_router)

jinja_env = Environment(loader=FileSystemLoader(str(BASE_DIR / "web" / "templates")), auto_reload=True)

PROTECTED_PATHS = {"/", "/config", "/config/users", "/config/hierarchy", "/config/assets", "/sensor-input", "/map", "/asset", "/admin", "/reports", "/tunnel"}
ADMIN_PATHS = {"/config", "/config/users", "/config/hierarchy", "/config/assets", "/admin"}


async def require_auth(request: Request):
    """Check if the user is authenticated. Returns a RedirectResponse if not."""
    if request.url.path not in PROTECTED_PATHS:
        return None
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    role = request.session.get("role", "")
    path = request.url.path
    if path in ADMIN_PATHS and role not in ("admin", "supervisor"):
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
@limiter.limit("10/minute")
async def login_post(request: Request):
    """Handle login form submission. Validates credentials against the DB User model."""
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    user = kb.get_user(username)
    if user and _verify_password(password, user.password_hash):
        request.session["user"] = username
        request.session["role"] = user.role
        request.session["condominium_ids"] = [c.id for c in user.condominiums]
        kb.add_audit(username, "login", "Inicio de sesión", user_id=user.id)
        return RedirectResponse(url="/", status_code=303)
    template = jinja_env.get_template("login.html")
    return HTMLResponse(template.render({"error": "Usuario o contraseña incorrectos"}))


@app.get("/logout")
async def logout(request: Request):
    """Clear the session, clear SW cache, and redirect to login."""
    request.session.clear()
    return HTMLResponse("""<!DOCTYPE html>
<html><body><script>
navigator.serviceWorker.ready.then(function(reg) {
    if (reg.active) reg.active.postMessage({action: "clear-cache"});
});
setTimeout(function() { window.location.href = "/login"; }, 100);
</script></body></html>""")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render the main monitoring dashboard with server-injected asset data."""
    import json
    from web.api import _build_full_data, simulator, event_cache, action_cache
    from core.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()
    template = jinja_env.get_template("dashboard.html")
    assets_data = _build_full_data()
    if not assets_data:
        for asset in kb.get_all_assets():
            assets_data[asset.name] = {
                "id": asset.id, "name": asset.label, "has_data": False,
                "sensors": {}, "sensors_meta": {}, "is_simulated": {},
                "all_simulated": True, "actuators": [],
                "score": 0, "status": "none",
                "recommendations": [], "explanation": "Sin datos aún",
                "scenarios": simulator.get_scenarios_list(asset.name),
                "current_scenario": "normal",
            }
    hierarchy = kb.get_full_hierarchy()
    role = request.session.get("role", "")
    if role in ("technician", "supervisor"):
        allowed_ids = request.session.get("condominium_ids", [])
        hierarchy = [c for c in hierarchy if c["id"] in allowed_ids]
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": role,
        "condominium_ids": request.session.get("condominium_ids", []),
        "hierarchy_json": json.dumps(hierarchy),
    }))




@app.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Render the configuration page (rules, sensors, membership functions)."""
    template = jinja_env.get_template("config.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "condominium_id": request.session.get("condominium_id"),
    }))


@app.get("/config/users", response_class=HTMLResponse)
async def config_users_page(request: Request):
    """Render the user management page."""
    template = jinja_env.get_template("config_users.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "condominium_id": request.session.get("condominium_id"),
    }))


@app.get("/config/hierarchy", response_class=HTMLResponse)
async def config_hierarchy_page(request: Request):
    """Render the hierarchy management page."""
    template = jinja_env.get_template("config_hierarchy.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/config/assets", response_class=HTMLResponse)
async def config_assets_page(request: Request):
    """Render the asset management page."""
    template = jinja_env.get_template("config_assets.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
    }))


@app.get("/sensor-input", response_class=HTMLResponse)
async def sensor_input_page(request: Request):
    """Render the mobile sensor input page for manual/phone sensor data."""
    template = jinja_env.get_template("sensor_input.html")
    import json
    from storage.database import SessionLocal
    from models.models import Asset, SensorConfig
    from core.knowledge_base import KnowledgeBase
    kb = KnowledgeBase()

    # Build hierarchy with full sensor configs for each asset
    condos = kb.get_all_condominiums()
    role = request.session.get("role", "")
    if role in ("technician", "supervisor"):
        allowed_ids = request.session.get("condominium_ids", [])
        condos = [c for c in condos if c.id in allowed_ids]
    hierarchy = []
    for c in condos:
        buildings = kb.get_buildings(c.id)
        b_list = []
        for b in buildings:
            rooms = kb.get_rooms(b.id)
            r_list = []
            for r in rooms:
                assets = kb.get_assets_in_room(r.id)
                a_list = []
                for a in assets:
                    sensors = kb.get_sensors(a.id)
                    sensors_data = []
                    for s in sensors:
                        sensors_data.append({
                            "id": s.id, "name": s.name, "label": s.label,
                            "unit": s.unit, "sensor_type": s.sensor_type,
                            "min_val": s.min_val, "max_val": s.max_val,
                            "mf_config": s.mf_config
                        })
                    a_list.append({
                        "id": a.id, "name": a.name, "label": a.label,
                        "icon": a.icon, "sensors": sensors_data
                    })
                r_list.append({
                    "id": r.id, "name": r.name, "assets": a_list
                })
            b_list.append({
                "id": b.id, "name": b.name, "rooms": r_list
            })
        c_data = {"id": c.id, "name": c.name, "icon": "🏢", "buildings": b_list}
        hierarchy.append(c_data)

    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "hierarchy_json": json.dumps(hierarchy),
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
    """Render the admin dashboard (audit log + hierarchy tree)."""
    template = jinja_env.get_template("admin.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "condominium_id": request.session.get("condominium_id"),
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


@app.get("/service-worker.js")
async def service_worker(request: Request):
    """Serve the service worker from the root scope so it controls all pages."""
    sw_path = BASE_DIR / "static" / "service-worker.js"
    if not sw_path.exists():
        return PlainTextResponse("", status_code=404)
    content = sw_path.read_text(encoding="utf-8")
    from starlette.responses import Response
    return Response(
        content=content,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/tunnel", response_class=HTMLResponse)
async def tunnel_page(request: Request):
    """Show the tunnel URL and QR code for mobile access."""
    tunnel_url = ""
    tunnel_file = BASE_DIR / "tunnel_url.txt"
    if tunnel_file.exists():
        tunnel_url = tunnel_file.read_text().strip()
    template = jinja_env.get_template("tunnel.html")
    return HTMLResponse(template.render({
        "request": request,
        "user": request.session.get("user"),
        "role": request.session.get("role"),
        "condominium_ids": request.session.get("condominium_ids", []),
    }))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
