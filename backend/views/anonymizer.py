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
import threading
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.components import CustomAnalyzer
from backend.components.image_sanitizer import (
    ImageSanitizerError,
    sanitize_image_base64,
)
from backend.database import SessionLocal
from backend.ocr_settings import get_ocr_settings
from backend.security import require_api_key
from backend.tracing import record_trace

# Router Blueprint
entityguard_router = APIRouter(prefix="/api/v1", tags=["Anonymizer"])

# Logger
logger = logging.getLogger("uvicorn.error")

# Lazily-created singleton analyzer, rebuilt on /reload
_analyzer: Optional[CustomAnalyzer] = None
# The endpoints run in a threadpool, so two first requests could build the
# analyzer (and load the spaCy model) twice without this lock.
_analyzer_lock = threading.Lock()


def _get_or_create_analyzer() -> CustomAnalyzer:
    """
    Get or create the analyzer.

    The analyzer is cached and reloaded from the database on /reload.
    """
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                db = SessionLocal()
                try:
                    _analyzer = CustomAnalyzer(language="de", db=db)
                    logger.info("Created analyzer")
                finally:
                    db.close()
    return _analyzer


class SanitizeRequest(BaseModel):
    """
    Request model for text sanitization.

    Attributes:
        text (str): The text to be anonymized.
        reuse_placeholders (bool): When true, identical values of the same
            entity type get the same placeholder within this request
            (``[NAME_1]`` for every "Max Mustermann") and the mapping has one
            entry per distinct value. Default false: one unique placeholder
            per occurrence. Useful when several messages of one conversation
            are sent as a single text, so a model can tell it is one person.
    """
    text: str
    reuse_placeholders: bool = False


class SanitizeResponse(BaseModel):
    """
    Response model for text sanitization.

    Attributes:
        sanitized_text (str): The anonymized text with sensitive entities masked.
        mapping (dict[str, str]): Mapping of placeholder to original value,
            for each masked entity occurrence.
    """
    sanitized_text: str
    mapping: dict[str, str]


class ImageSanitizeRequest(BaseModel):
    """Request model for image sanitization.

    ``image_base64`` accepts raw base64 or a complete data URI
    (``data:image/png;base64,...``). ``reuse_placeholders`` defaults to true
    because screenshots often repeat the same value.
    """
    image_base64: str
    mime_type: Optional[str] = None
    reuse_placeholders: bool = True


class ImageSanitizeResponse(BaseModel):
    """Response model for image sanitization.

    ``sanitized_image_base64`` is a PNG without metadata. ``redactions`` and
    ``entities`` are only for the admin preview; API clients can ignore them.
    """
    sanitized_image_base64: str
    sanitized_text: str
    ocr_text: str
    mapping: dict[str, str]
    ocr_engine: str
    ocr_device: str
    ocr_confidence: float
    latency_ms: float
    image_width: int
    image_height: int
    redactions: list[dict]
    entities: list[dict]
    warnings: list[str]


class ReloadResponse(BaseModel):
    """
    Response model for pattern reload.

    Attributes:
        success (bool): Whether the reload was successful.
        recognizers_count (int): Number of recognizers loaded.
        message (str): Status message.
    """
    success: bool
    recognizers_count: int
    message: str


@entityguard_router.post("/sanitize/image", response_model=ImageSanitizeResponse)
def sanitize_image(request: ImageSanitizeRequest, api_key=Depends(require_api_key)):
    """
    OCR an image, mask recognized text entities and return a redacted PNG.

    The image is processed in memory only. The response contains the redacted
    image as base64 PNG plus the OCR text and its placeholder mapping. The raw
    image is never returned on failure (fail-closed).

    Like ``/sanitize`` this is a plain ``def`` so the CPU-bound OCR and NLP
    work runs in the threadpool instead of blocking the event loop.
    """
    start = time.perf_counter()
    db = SessionLocal()
    try:
        settings = get_ocr_settings(db)
    finally:
        db.close()

    if not settings.enabled:
        raise HTTPException(status_code=404, detail="Bildverarbeitung ist deaktiviert")

    try:
        result = sanitize_image_base64(
            request.image_base64,
            _get_or_create_analyzer(),
            settings,
            reuse_placeholders=request.reuse_placeholders,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        record_trace(
            "api-image",
            result.ocr_text,
            result.mapping,
            latency_ms,
            True,
            api_key_prefix=(api_key or {}).get("key_prefix"),
        )
        return ImageSanitizeResponse(
            sanitized_image_base64=result.sanitized_image_base64,
            sanitized_text=result.sanitized_text,
            ocr_text=result.ocr_text,
            mapping=result.mapping,
            ocr_engine=result.ocr_engine,
            ocr_device=result.ocr_device,
            ocr_confidence=result.ocr_confidence,
            latency_ms=latency_ms,
            image_width=result.image_width,
            image_height=result.image_height,
            redactions=result.redactions,
            entities=result.entities,
            warnings=result.warnings,
        )
    except ImageSanitizerError as e:
        logger.error("Image sanitization failed: %s", e)
        record_trace(
            "api-image", "", {}, (time.perf_counter() - start) * 1000, False,
            api_key_prefix=(api_key or {}).get("key_prefix"),
        )
        raise HTTPException(status_code=e.status_code, detail=e.public_message)
    except Exception as e:
        logger.error("Error in image sanitization: %s", e)
        record_trace(
            "api-image", "", {}, (time.perf_counter() - start) * 1000, False,
            api_key_prefix=(api_key or {}).get("key_prefix"),
        )
        raise HTTPException(status_code=500, detail="Security abort: Image sanitization failed")


@entityguard_router.post("/reload", response_model=ReloadResponse)
def reload_patterns(api_key=Depends(require_api_key)):
    """
    Reload pattern recognizers from the database.

    This endpoint allows hot-reloading of patterns after modifying
    the database via the admin interface. It clears the cached
    analyzers and reloads from the database on next request.

    Requires a valid API key (see the API-keys page in the admin UI).

    Returns:
        ReloadResponse: Status of the reload operation.

    Raises:
        HTTPException: Status code 401 if no valid API key is supplied,
            status code 500 if the reload fails.
    """
    global _analyzer
    try:
        # Create a fresh analyzer to verify it works and get count
        db = SessionLocal()
        try:
            analyzer = CustomAnalyzer(language="de", db=db)
            recognizers_list = list(analyzer.analyzer.registry.recognizers)
            # Subtract built-in recognizers (spacy_nlp, pattern_recognizer)
            custom_count = max(0, len(recognizers_list) - 1)
            _analyzer = analyzer
            return ReloadResponse(
                success=True,
                recognizers_count=custom_count,
                message=f"Successfully reloaded {custom_count} recognizers from database"
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error reloading patterns: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload patterns: {str(e)}"
        )


@entityguard_router.post("/sanitize", response_model=SanitizeResponse)
def sanitize(request: SanitizeRequest, api_key=Depends(require_api_key)):
    """
    Receive text and return the anonymized version along with a mapping.

    This endpoint accepts text input and processes it through the CustomAnalyzer
    to detect and mask sensitive entities. The response includes a mapping of
    placeholder to original value for each masked entity occurrence, allowing
    the masked text to be de-anonymized later.

    Requires a valid API key (see the API-keys page in the admin UI).

    Deliberately a plain ``def`` (not ``async def``): the analysis (spaCy,
    Presidio) is CPU-bound and blocking, so FastAPI runs it in its worker
    threadpool. As ``async def`` it would freeze the whole event loop - every
    other request, ``/health`` included - for the duration of each call, which
    matters for long texts such as a whole chat history.

    Args:
        request (SanitizeRequest): The sanitization request containing text.

    Returns:
        SanitizeResponse: The anonymized text and the placeholder-to-original mapping.

    Raises:
        HTTPException: Status code 401 if no valid API key is supplied,
            status code 500 if the sanitization process fails.
            Implements fail-closed principle - returns error instead of
            passing through unprocessed text.
    """
    try:
        start = time.perf_counter()
        analyzer = _get_or_create_analyzer()

        sanitized_text, mapping = analyzer.process_text(
            request.text, reuse_placeholders=request.reuse_placeholders
        )

        record_trace(
            "api",
            request.text,
            mapping,
            (time.perf_counter() - start) * 1000,
            True,
            api_key_prefix=(api_key or {}).get("key_prefix"),
        )

        return SanitizeResponse(
            sanitized_text=sanitized_text,
            mapping=mapping
        )

    except Exception as e:
        logger.error(f"Error in guardrail routing: {e}")
        raise HTTPException(
            status_code=500,
            detail="Security abort: Data sanitization failed"
        )