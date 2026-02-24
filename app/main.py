from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import get_websocket_user
from app.config import settings
from app.database import SessionLocal, get_db
from app.models import AuditLog
from app.routers import analytics, audit, auth, inventory, menu, orders, shift
from app.seed import seed_database
from app.services.rate_limit import login_rate_limiter
from app.ws import manager

logger = logging.getLogger(__name__)


def clear_rate_limits() -> None:
    """Clear all rate limit state. Used by tests."""
    login_rate_limiter.clear_local()


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        try:
            db.execute(select(AuditLog.id).limit(1)).all()
            seed_database(db)
        except SQLAlchemyError as exc:
            raise RuntimeError(
                "Database schema is not ready. Run 'alembic upgrade head' first.",
            ) from exc
    try:
        yield
    finally:
        await login_rate_limiter.close()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

# ---------------------------------------------------------------------------
# CORS — refuse wildcard in production
# ---------------------------------------------------------------------------
if settings.cors_origins:
    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
else:
    origins = []

if not origins and not settings.is_production:
    origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security headers middleware (CSP, etc.)
# ---------------------------------------------------------------------------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'"
    )
    if not request.url.path.startswith("/api") and not request.url.path.startswith("/ws"):
        # Prevent stale frontend bundles on cashier devices.
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# ---------------------------------------------------------------------------
# Login rate-limit moved to auth.login for identity-aware control
# ---------------------------------------------------------------------------
app.include_router(menu.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(shift.router, prefix="/api")


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/api/config/public")
def public_config() -> dict:
    """Expose non-sensitive config to frontend."""
    return {"env": settings.app_env, "auth_disabled": settings.auth_disabled}


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    with SessionLocal() as db:
        get_websocket_user(token=token, db=db)

    await manager.connect(websocket)
    await websocket.send_json({"event": "connected"})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/pos", StaticFiles(directory=frontend_dir / "pos", html=True), name="pos")
app.mount("/kds", StaticFiles(directory=frontend_dir / "kds", html=True), name="kds")
app.mount("/pickup", StaticFiles(directory=frontend_dir / "pickup", html=True), name="pickup")
app.mount("/admin", StaticFiles(directory=frontend_dir / "admin", html=True), name="admin")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
