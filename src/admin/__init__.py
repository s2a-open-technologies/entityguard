"""
Admin package for the admin interface.

This package provides authentication, routes, and dependencies
for the admin interface that manages pattern recognizers.
"""

from .routes import admin_router
from .auth import get_current_user, require_auth

__all__ = ["admin_router", "get_current_user", "require_auth"]