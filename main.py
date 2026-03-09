"""
Medical Chat Sanitizer - FastAPI Application Entry Point.

This module provides the main application factory for the FastAPI service
that anonymizes patient data according to GDPR and HIPAA regulations.
"""

import logging

import uvicorn
from fastapi import FastAPI

from src.views import guardrails_router

# Logger
logger = logging.getLogger("uvicorn.error")


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
        version="0.1.0"
    )

    app.include_router(guardrails_router)

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
    uvicorn.run(create_app, host="0.0.0.0", port=6000)
