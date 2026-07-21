"""
EntityGuard - FastAPI Application Entry Point.
Copyright (C) 2026  Christopher Abanilla

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.admin import admin_router, get_current_user
from src.views import entityguard_router, public_router

# Logger
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    The database schema and seed data are managed exclusively by Alembic.
    Run `uv run alembic upgrade head` before starting the application.
    """
    # Startup
    logger.info("EntityGuard starting up...")

    yield

    # Shutdown (if needed)
    logger.info("Shutting down...")


def create_app():
    """
    Create and configure the FastAPI application instance.

    Returns:
        FastAPI: Configured FastAPI application with registered routers
                 and health check endpoint.
    """
    app = FastAPI(
        title="EntityGuard",
        description="Security layer for processing patient data according to GDPR & HIPAA",
        version="1.0.0",
        lifespan=lifespan
    )

    # Mount static files
    static_dir = Path(__file__).parent / "src" / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routers
    app.include_router(entityguard_router)
    app.include_router(admin_router)
    app.include_router(public_router)

    @app.get("/health")
    async def health():
        """
        Health check endpoint.

        Returns:
            dict: Status indicator showing the service is running.
        """
        return {"status": "Service is running"}

    @app.get("/")
    async def root_redirect(request: Request):
        """Redirect root to the admin dashboard, or login if not authenticated."""
        if get_current_user(request):
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        return RedirectResponse(url="/admin/login", status_code=302)

    return app


if __name__ == "__main__":
    uvicorn.run(create_app, host="0.0.0.0", port=9500)
