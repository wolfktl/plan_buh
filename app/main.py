"""Точка входа FastAPI."""
import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .routers import (admin, auth, channels, counterparties, notes,
                      notifications, planner)
from .security import SESSION_COOKIE, _decode

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title=settings.APP_TITLE, docs_url="/api/docs", openapi_url="/api/openapi.json")

# Создаём таблицы при старте приложения (идемпотентно).
init_db()

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(counterparties.router)
app.include_router(planner.router)
app.include_router(notes.router)
app.include_router(notifications.router)
app.include_router(channels.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/version")
def version():
    return {"version": settings.APP_VERSION, "app": settings.APP_TITLE}


def _is_authed(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    p = _decode(token)
    return bool(p and p.get("scope") == "session")


@app.get("/")
def root(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/login")
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/login")
def login_page():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))


@app.get("/sw.js")
def service_worker():
    # Service Worker должен отдаваться с корня, чтобы иметь scope "/"
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"),
                        media_type="application/javascript")


# Статика (css/js/картинки при необходимости)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
