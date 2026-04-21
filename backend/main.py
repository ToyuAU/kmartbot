"""
FastAPI application factory.
Run with: python run.py  (or directly: uvicorn backend.main:app --reload)
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import aiosqlite

from backend.database import init_db, DB_PATH
from backend.config import config, apply_settings
from backend.api import profiles, cards, tasks, settings, ws
from backend.core import event_bus


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Overlay persisted dashboard settings on top of config.json defaults
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
    apply_settings({row["key"]: row["value"] for row in rows})

    # Register WebSocket broadcaster on the event bus
    from backend.api.ws import _broadcast
    event_bus.subscribe(_broadcast)

    yield

    # Shutdown
    from backend.core.task_manager import task_manager
    await task_manager.stop_all()


app = FastAPI(title="KmartBot", version="2.0.0", lifespan=lifespan)

# Allow the Vite dev server (port 5173) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(profiles.router)
app.include_router(cards.router)
app.include_router(tasks.router)
app.include_router(settings.router)
app.include_router(ws.router)

# Serve built Vite dashboard in production
DIST = Path(__file__).parent.parent / "dashboard" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="dashboard")
