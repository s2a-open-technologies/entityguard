"""
FastAPI router for the guardrails anonymization endpoint.

This module provides the API router with endpoints for text sanitization.
It handles incoming text and returns anonymized versions with sensitive
entities masked according to department-specific rules.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from src.components import CustomAnalyzer

# Router Blueprint
guardrails_router = APIRouter(prefix="/api/v1/guardrails", tags=["Anonymizer"])

# Logger
logger = logging.getLogger("uvicorn.error")

# Dynamic registration of pattern registry
_analyzer_registry = {
    "standard": CustomAnalyzer(language="de")
}


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


@guardrails_router.post("/sanitize", response_model=SanitizeResponse)
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
        analyzer = _analyzer_registry.get(
            request.department.lower(),
            _analyzer_registry["standard"]
        )

        result_text = analyzer.process_text(request.text)

        return SanitizeResponse(
            sanitized_text=result_text,
            applied_department=request.department
        )

    except Exception as e:
        logger.error(f"Error in guardrail routing: {e}")
        # Fail-Closed: If the service is not running, return error instead of passing through text
        return HTTPException(
            status_code=500,
            detail="Security abort: Data sanitization failed"
        )
