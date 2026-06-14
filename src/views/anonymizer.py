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

# Dynamic registration of pattern registry
_analyzer_registry: dict[str, CustomAnalyzer] = {}


def _get_or_create_analyzer(department: str = "standard") -> CustomAnalyzer:
    """
    Get or create an analyzer for the given department.

    Analyzers are cached in the registry and reloaded from database
    when they don't exist.
    """
    if department not in _analyzer_registry:
        db = SessionLocal()
        try:
            _analyzer_registry[department] = CustomAnalyzer(language="de", db=db)
            logger.info(f"Created analyzer for department '{department}'")
        finally:
            db.close()
    return _analyzer_registry[department]


class SanitizeRequest(BaseModel):
    """
    Request model for text sanitization.

    Attributes:
        text (str): The text to be anonymized.
        department (Optional[str]): Department-specific rule set to apply.
            Defaults to "standard".
    """
    text: str
    department: Optional[str] = "standard"


class SanitizeResponse(BaseModel):
    """
    Response model for text sanitization.

    Attributes:
        sanitized_text (str): The anonymized text with sensitive entities masked.
        applied_department (str): The department rule set that was applied.
    """
    sanitized_text: str
    applied_department: str


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
    try:
        # Clear all cached analyzers - they will be recreated on next request
        _analyzer_registry.clear()

        # Create a fresh analyzer to verify it works and get count
        db = SessionLocal()
        try:
            analyzer = CustomAnalyzer(language="de", db=db)
            recognizers_list = list(analyzer.analyzer.registry.recognizers)
            # Subtract built-in recognizers (spacy_nlp, pattern_recognizer)
            custom_count = max(0, len(recognizers_list) - 1)
            _analyzer_registry["standard"] = analyzer
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
    Receive text and return the anonymized version.

    This endpoint accepts text input and processes it through the CustomAnalyzer
    to detect and mask sensitive entities. The department parameter allows for
    department-specific guardrail rules to be applied.

    Args:
        request (SanitizeRequest): The sanitization request containing text
            and optional department identifier.

    Returns:
        SanitizeResponse: The anonymized text and the applied department identifier.

    Raises:
        HTTPException: Status code 500 if the sanitization process fails.
            Implements fail-closed principle - returns error instead of
            passing through unprocessed text.
    """
    try:
        department = request.department or "standard"
        analyzer = _get_or_create_analyzer(department)

        result_text = analyzer.process_text(request.text)

        return SanitizeResponse(
            sanitized_text=result_text,
            applied_department=department
        )

    except Exception as e:
        logger.error(f"Error in guardrail routing: {e}")
        raise HTTPException(
            status_code=500,
            detail="Security abort: Data sanitization failed"
        )