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
from datetime import datetime, timedelta
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.admin import admin_router, get_current_user
from backend.components.bert_recognizer import BERT_MODEL_REGISTRY, resolve_model_keys
from backend.config import (
    ADMIN_PASSWORD_FROM_ENV, ADMIN_USERNAME_FROM_ENV, MODELS_FROM_ENV,
    TRACE_ENABLED, TRACE_RETENTION_DAYS,
)
from backend.database import SessionLocal
from backend.database.crud import (
    delete_old_request_traces, ensure_env_admin, log_audit, sync_detector_models,
)
from backend.views import entityguard_router

# Logger
logger = logging.getLogger("uvicorn.error")


def _cleanup_request_traces() -> None:
    """Prune request traces older than TRACE_RETENTION_DAYS (best-effort)."""
    if not TRACE_ENABLED:
        return
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=TRACE_RETENTION_DAYS)
        removed = delete_old_request_traces(db, cutoff)
        if removed:
            logger.info(f"Pruned {removed} request trace(s) older than {TRACE_RETENTION_DAYS} days")
    except Exception as e:
        logger.warning(f"Request-trace cleanup failed: {e}")
    finally:
        db.close()


def _apply_env_admin() -> None:
    """Create/update the admin account from ENTITYGUARD_ADMIN_PASSWORD (if set)."""
    if not ADMIN_PASSWORD_FROM_ENV:
        return
    db = SessionLocal()
    try:
        result = ensure_env_admin(db, ADMIN_USERNAME_FROM_ENV, ADMIN_PASSWORD_FROM_ENV)
        if result:
            logger.info(f"Admin account '{ADMIN_USERNAME_FROM_ENV}' {result} from ENTITYGUARD_ADMIN_PASSWORD")
    except Exception as e:
        logger.error(f"Applying ENTITYGUARD_ADMIN_PASSWORD failed: {e}")
    finally:
        db.close()


def _apply_env_models() -> None:
    """Activate exactly the transformer models listed in ENTITYGUARD_MODELS (if set)."""
    if MODELS_FROM_ENV is None:
        return
    keys, unknown = resolve_model_keys(MODELS_FROM_ENV)
    if unknown:
        logger.error(
            f"ENTITYGUARD_MODELS: unknown model(s) {unknown} ignored "
            f"(available: {list(BERT_MODEL_REGISTRY)})"
        )
    db = SessionLocal()
    try:
        changed = sync_detector_models(db, list(BERT_MODEL_REGISTRY), keys)
        for key in changed:
            log_audit(
                db, action="toggle",
                summary=f"Modell '{key}' per ENTITYGUARD_MODELS {'aktiviert' if key in keys else 'deaktiviert'}",
                actor_username="ENV", target_type="detector_model", target_label=key,
            )
        logger.info(f"Transformer models from ENTITYGUARD_MODELS: {keys or 'none'}")
    except Exception as e:
        logger.error(f"Applying ENTITYGUARD_MODELS failed: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    The database schema and seed data are managed exclusively by Alembic.
    Run `uv run alembic upgrade head` before starting the application.
    """
    # Startup
    logger.info("EntityGuard starting up...")
    _apply_env_admin()
    _apply_env_models()
    _cleanup_request_traces()

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
        version="1.2.1",
        lifespan=lifespan
    )

    # Mount static files
    static_dir = Path(__file__).parent / "frontend" / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include routers
    app.include_router(entityguard_router)
    app.include_router(admin_router)

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
