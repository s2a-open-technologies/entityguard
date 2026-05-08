"""
Dependencies for the admin interface templates.

This module provides helper functions for rendering templates with
common context data.
"""

from fastapi import Request
from typing import Any

from .auth import get_current_user

def get_template_context(request: Request, **kwargs: Any) -> dict:
    """
    Build the template context with common data.

    Args:
        request: The FastAPI request object.
        **kwargs: Additional context variables.

    Returns:
        dict: The template context dictionary.
    """

    context = {
        "request": request,
        "user": get_current_user(request),
        **kwargs
    }
    return context