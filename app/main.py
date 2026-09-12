"""TransiPulse — FastAPI async application entry point."""

from __future__ import annotations

import contextlib

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import dispose_db, init_db
from app.core.logging import logger

# Routers
from app.api import feedback, routes, trips, analytics, ai

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.debug("Database URL: %s", settings.database_url)
    logger.debug("Debug mode: %s", settings.debug)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await dispose_db()
    logger.info("Bye!")


app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback"])
app.include_router(routes.router, prefix="/api/v1/routes", tags=["Routes"])
app.include_router(trips.router, prefix="/api/v1/trips", tags=["Trips"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["AI"])

# ---------------------------------------------------------------------------
# Static files & Frontend routes
# ---------------------------------------------------------------------------
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/dashboard", tags=["Frontend"])
async def dashboard_page():
    return FileResponse(static_dir / "dashboard.html")

@app.get("/commuter", tags=["Frontend"])
async def commuter_page():
    return FileResponse(static_dir / "commuter.html")

# ---------------------------------------------------------------------------
# Root endpoint
# ---------------------------------------------------------------------------
@app.get("/", tags=["Root"])
async def root() -> dict[str, str]:
    """Health check / welcome endpoint."""
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
        "redoc": "/redoc",
        "dashboard": "/dashboard",
        "commuter": "/commuter",
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )