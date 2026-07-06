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
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.components import CustomAnalyzer
from src.database import SessionLocal

# Router Blueprint
entityguard_router = APIRouter(prefix="/api/v1/entityguard", tags=["Anonymizer"])

# Logger
logger = logging.getLogger("uvicorn.error")

# Lazily-created singleton analyzer, rebuilt on /reload
_analyzer: Optional[CustomAnalyzer] = None


def _get_or_create_analyzer() -> CustomAnalyzer:
    """
    Get or create the analyzer.

    The analyzer is cached and reloaded from the database on /reload.
    """
    global _analyzer
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
    """
    text: str


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


@entityguard_router.post("/reload", response_model=ReloadResponse)
async def reload_patterns():
    """
    Reload pattern recognizers from the database.

    This endpoint allows hot-reloading of patterns after modifying
    the database via the admin interface. It clears the cached
    analyzers and reloads from the database on next request.

    Returns:
        ReloadResponse: Status of the reload operation.

    Raises:
        HTTPException: Status code 500 if the reload fails.
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
async def sanitize(request: SanitizeRequest):
    """
    Receive text and return the anonymized version along with a mapping.

    This endpoint accepts text input and processes it through the CustomAnalyzer
    to detect and mask sensitive entities. The response includes a mapping of
    placeholder to original value for each masked entity occurrence, allowing
    the masked text to be de-anonymized later.

    Args:
        request (SanitizeRequest): The sanitization request containing text.

    Returns:
        SanitizeResponse: The anonymized text and the placeholder-to-original mapping.

    Raises:
        HTTPException: Status code 500 if the sanitization process fails.
            Implements fail-closed principle - returns error instead of
            passing through unprocessed text.
    """
    try:
        analyzer = _get_or_create_analyzer()

        sanitized_text, mapping = analyzer.process_text(request.text)

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