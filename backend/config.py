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

import os


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


# Tracing-lite: record content-free per-request metadata (see
# RequestTraceModel). Enabled by default; disable via TRACE_ENABLED=false.
TRACE_ENABLED: bool = _env_bool("TRACE_ENABLED", True)

# Days a request_trace row is kept before the startup cleanup removes it.
TRACE_RETENTION_DAYS: int = _env_int("TRACE_RETENTION_DAYS", 7)

# Secret for the optional keyed input hash (HMAC-SHA256). When unset, no
# hash is written at all - keeping the trace even more minimal.
TRACE_HMAC_SECRET: str | None = os.getenv("TRACE_HMAC_SECRET") or None
