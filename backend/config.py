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
import os

logger = logging.getLogger("uvicorn.error")


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable (1/true/yes/on)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable, falling back on error."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_MIN_ENV_KEY_LENGTH = 16
_MIN_ADMIN_PASSWORD_LENGTH = 8  # same rule as the admin UI password forms


def _env_or_file(name: str) -> str:
    """
    Read NAME plus the contents of the file named by NAME_FILE (Docker-secrets
    convention), joined by a newline when both are set.
    """
    values = [os.getenv(name, "")]
    path = os.getenv(f"{name}_FILE")
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                values.append(fh.read())
        except OSError as exc:
            logger.error("%s_FILE unreadable (%s): %s", name, path, exc)
    return "\n".join(v for v in values if v)


def _split_keys(raw: str) -> list[str]:
    """Split a comma- or newline-separated key list, dropping blanks."""
    return [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]


def _env_api_keys() -> list[str]:
    """
    Collect API keys from ENTITYGUARD_API_KEY and ENTITYGUARD_API_KEY_FILE.

    Both may hold several keys (comma or newline separated); the file variant
    follows the Docker-secrets convention. Keys shorter than
    _MIN_ENV_KEY_LENGTH are rejected so trivial values like "test" can never
    open the API.
    """
    keys = _split_keys(_env_or_file("ENTITYGUARD_API_KEY"))

    valid = []
    for key in keys:
        if len(key) < _MIN_ENV_KEY_LENGTH:
            logger.error(
                "Ignoring API key from environment: shorter than %d characters",
                _MIN_ENV_KEY_LENGTH,
            )
        elif key not in valid:
            valid.append(key)
    return valid


# API keys supplied via environment (headless/Docker setups without access to
# the admin UI). Accepted in addition to the active DB keys, never stored.
API_KEYS_FROM_ENV: list[str] = _env_api_keys()


def _env_admin_password() -> str | None:
    """
    Read ENTITYGUARD_ADMIN_PASSWORD (or _FILE). Surrounding whitespace, e.g.
    the trailing newline of a secret file, is stripped. Too short -> ignored.
    """
    password = _env_or_file("ENTITYGUARD_ADMIN_PASSWORD").strip()
    if not password:
        return None
    if len(password) < _MIN_ADMIN_PASSWORD_LENGTH:
        logger.error(
            "Ignoring ENTITYGUARD_ADMIN_PASSWORD: shorter than %d characters",
            _MIN_ADMIN_PASSWORD_LENGTH,
        )
        return None
    return password


# Admin account managed via environment (headless/Docker). When the password
# is set, startup creates or updates this user (see main.py); unset = no-op.
ADMIN_USERNAME_FROM_ENV: str = os.getenv("ENTITYGUARD_ADMIN_USERNAME", "").strip() or "admin"
ADMIN_PASSWORD_FROM_ENV: str | None = _env_admin_password()

# Transformer models to activate at startup (comma-separated registry keys or
# their short form, e.g. "openmed_small"; "none" disables all). Unset = the
# DB toggles from /admin/modelle stay as they are. Resolved in main.py.
MODELS_FROM_ENV: str | None = os.getenv("ENTITYGUARD_MODELS")

# Tracing-lite: record content-free per-request metadata (see
# RequestTraceModel). Enabled by default; disable via TRACE_ENABLED=false.
TRACE_ENABLED: bool = _env_bool("TRACE_ENABLED", True)

# Days a request_trace row is kept before the startup cleanup removes it.
TRACE_RETENTION_DAYS: int = _env_int("TRACE_RETENTION_DAYS", 7)

# Secret for the optional keyed input hash (HMAC-SHA256). When unset, no
# hash is written at all - keeping the trace even more minimal.
TRACE_HMAC_SECRET: str | None = os.getenv("TRACE_HMAC_SECRET") or None
