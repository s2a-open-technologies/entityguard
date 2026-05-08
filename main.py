"""
Medical Chat Sanitizer - FastAPI Application Entry Point.

This module provides the main application factory for the FastAPI service
that anonymizes patient data according to GDPR and HIPAA regulations.
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.views import entityguard_router
from src.admin import admin_router
from src.database import init_db, SessionLocal
from src.database.crud import get_admin_user_by_username, create_admin_user
from src.database.seed import seed_database

# Logger
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Handles:
    - Database initialization
    - Default admin user seeding
    """
    # Startup
    logger.info("Initializing database...")
    init_db()

    # Seed default admin user if not exists
    db = SessionLocal()
    try:
        existing_admin = get_admin_user_by_username(db, "admin")
        if not existing_admin:
            create_admin_user(db, "admin", "admin")
            logger.info("Created default admin user (admin:admin)")
        else:
            logger.info("Admin user already exists")

        # Seed default data (entities and recognizers)
        seed_database(db)
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
    finally:
        db.close()

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
        title="Medical Chat Sanitizer",
        description="Security layer for processing patient data according to GDPR & HIPAA",
        version="0.1.0",
        lifespan=lifespan
    )

    # Mount static files
    static_dir = Path(__file__).parent / "static"
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

    return app


if __name__ == "__main__":
    uvicorn.run(create_app, host="0.0.0.0", port=9000)
