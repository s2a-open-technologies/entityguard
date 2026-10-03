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

import hashlib
import hmac as hmac_lib
import json
import logging
import re

from backend.config import TRACE_ENABLED, TRACE_HMAC_SECRET
from backend.database import SessionLocal
from backend.database.crud import create_request_trace

logger = logging.getLogger("uvicorn.error")


def _strip_index(placeholder: str) -> str:
    """Turn an indexed placeholder ('[EMAIL_1]') into its base type ('EMAIL')."""
    base = placeholder
    if base.startswith("["):
        base = base[1:]
    if base.endswith("]"):
        base = base[:-1]
    return re.sub(r"_\d+$", "", base) or placeholder


def record_trace(
    source: str,
    input_text: str,
    mapping: dict[str, str],
    latency_ms: float,
    success: bool,
    api_key_prefix: str | None = None,
) -> None:
    """Write one content-free request trace row (best-effort).

    Never stores the text or the mapping - only counts and, if
    TRACE_HMAC_SECRET is set, a keyed hash of the input. Disabled entirely
    when TRACE_ENABLED is false. Any failure is logged and swallowed so
    tracing can never break sanitization.
    """
    if not TRACE_ENABLED:
        return

    entity_counts: dict[str, int] = {}
    for placeholder in mapping:
        base = _strip_index(placeholder)
        entity_counts[base] = entity_counts.get(base, 0) + 1

    input_hmac = None
    if TRACE_HMAC_SECRET:
        input_hmac = hmac_lib.new(
            TRACE_HMAC_SECRET.encode("utf-8"),
            input_text.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    db = SessionLocal()
    try:
        create_request_trace(
            db,
            source=source,
            input_length=len(input_text),
            mask_count=len(mapping),
            entity_counts=json.dumps(entity_counts, ensure_ascii=False) if entity_counts else None,
            latency_ms=round(latency_ms, 2),
            success=success,
            api_key_prefix=api_key_prefix,
            input_hmac=input_hmac,
        )
    except Exception as e:
        logger.warning(f"Could not write request trace: {e}")
    finally:
        db.close()
