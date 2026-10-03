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

import logging
import re
import secrets

import bcrypt
from fastapi import HTTPException, Request, status

from backend.database import SessionLocal
from backend.database.crud import get_active_api_keys, touch_api_key
from backend.database.models import ApiKeyModel

logger = logging.getLogger("uvicorn.error")

# Key format: eg_<app-slug>_<random token>. The eg_ prefix makes keys
# recognizable, the slug maps a key back to its app ("Bezeichnung").
KEY_PREFIX = "eg"


def _slugify(name: str) -> str:
    """Turn an app label into a short, URL-safe slug for the key prefix."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "key"


def generate_api_key(name: str) -> tuple[str, str, str]:
    """
    Generate a new API key for the given app label.

    Returns:
        tuple[str, str, str]: (plaintext key, display prefix, bcrypt hash).
            The plaintext is returned only here and must be shown to the
            user exactly once - it cannot be recovered later.
    """
    token = secrets.token_urlsafe(32)
    slug = _slugify(name)
    plaintext = f"{KEY_PREFIX}_{slug}_{token}"
    prefix = f"{KEY_PREFIX}_{slug}_{token[:6]}"
    key_hash = bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return plaintext, prefix, key_hash


def _extract_key(request: Request) -> str | None:
    """Read the API key from an Authorization: Bearer or X-API-Key header."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    header_key = request.headers.get("X-API-Key")
    if header_key:
        return header_key.strip()

    return None


def require_api_key(request: Request) -> dict:
    """
    FastAPI dependency: authenticate a request against the stored API keys.

    Accepts the key either as ``Authorization: Bearer <key>`` or as an
    ``X-API-Key`` header. Only active keys from the database are accepted -
    there is no environment fallback. While no active key exists, every
    request is rejected with HTTP 401 (fail-closed).

    Args:
        request: The incoming FastAPI request.

    Returns:
        dict: Basic info about the matching key (id, name, key_prefix).

    Raises:
        HTTPException: 401 if the header is missing, malformed or unknown.
    """
    provided = _extract_key(request)

    with SessionLocal() as db:
        active_keys = get_active_api_keys(db)
        if not active_keys:
            logger.warning("API request rejected: no active API key configured")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: no API key configured",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if provided:
            for api_key in active_keys:
                if bcrypt.checkpw(provided.encode("utf-8"), api_key.key_hash.encode("utf-8")):
                    touch_api_key(db, api_key.id)
                    # Return plain values: the ORM instance is detached once
                    # this session closes and must not be accessed later.
                    return {
                        "id": api_key.id,
                        "name": api_key.name,
                        "key_prefix": api_key.key_prefix,
                    }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
