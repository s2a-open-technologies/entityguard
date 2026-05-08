"""
Database package for the admin interface.

This package provides SQLAlchemy models, database session management,
and CRUD operations for the admin interface.
"""

from .database import SessionLocal, engine, get_db, init_db
from .models import Base, RecognizerModel, PatternModel, ContextWordModel, AdminUser, EntityModel
from .seed import seed_database

__all__ = [
    "SessionLocal", "engine", "get_db", "init_db",
    "Base", "RecognizerModel", "PatternModel", "ContextWordModel", "AdminUser", "EntityModel",
    "seed_database"
]