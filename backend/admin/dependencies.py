"""
.
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

from typing import Any

from fastapi import Request

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