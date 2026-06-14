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

import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from src.database import SessionLocal
from src.database.crud import authenticate_admin_user, get_admin_user


# In-memory session store (sufficient for single user)
# Maps session_id -> {user_id, expires_at}
_sessions: dict[str, dict] = {}

# Session configuration
SESSION_COOKIE_NAME = "admin_session"
SESSION_EXPIRY_HOURS = 8


def create_session(user_id: int) -> str:
    """
    Create a new session for a user.

    Args:
        user_id: The ID of the authenticated user.

    Returns:
        str: A new session ID.
    """
    session_id = secrets.token_urlsafe(32)
    expires_at = time.time() + (SESSION_EXPIRY_HOURS * 3600)
    _sessions[session_id] = {
        "user_id": user_id,
        "expires_at": expires_at
    }
    return session_id


def validate_session(session_id: str) -> Optional[int]:
    """
    Validate a session and return the user ID if valid.

    Args:
        session_id: The session ID to validate.

    Returns:
        Optional[int]: The user ID if the session is valid, None otherwise.
    """
    session = _sessions.get(session_id)
    if not session:
        return None

    if time.time() > session["expires_at"]:
        del _sessions[session_id]
        return None

    return session["user_id"]


def delete_session(session_id: str) -> None:
    """
    Delete a session (logout).

    Args:
        session_id: The session ID to delete.
    """
    _sessions.pop(session_id, None)


def get_current_user(request: Request) -> Optional[dict]:
    """
    Get the current user from the session cookie.

    This is a dependency that can be used to optionally get the user.

    Args:
        request: The FastAPI request object.

    Returns:
        Optional[dict]: The user info if authenticated, None otherwise.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None

    user_id = validate_session(session_id)
    if not user_id:
        return None

    with SessionLocal() as db:
        user = get_admin_user(db, user_id)
        if not user or not user.is_active:
            return None
        return {"id": user.id, "username": user.username}


def require_auth(request: Request) -> dict:
    """
    Require authentication for a route.

    This is a dependency that will raise an HTTPException if the user
    is not authenticated.

    Args:
        request: The FastAPI request object.

    Returns:
        dict: The user info if authenticated.

    Raises:
        HTTPException: If the user is not authenticated.
    """
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"}
        )
    return user


def authenticate_user(username: str, password: str) -> Optional[int]:
    """
    Authenticate a user by username and password.

    Args:
        username: The username to authenticate.
        password: The password to verify.

    Returns:
        Optional[int]: The user ID if authenticated, None otherwise.
    """
    with SessionLocal() as db:
        user = authenticate_admin_user(db, username, password)
        if user:
            return user.id
        return None