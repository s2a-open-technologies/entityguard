"""
Image text redaction: OCR, entity detection and black-box overlays.
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

import base64
import io
import logging
import time
from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from backend.components.cstm_analyzer import CustomAnalyzer
from backend.components.ocr import (
    OcrError,
    OcrLine,
    OcrResult,
    OcrTimeoutError,
    OcrToken,
    OcrUnavailableError,
    run_ocr,
)
from backend.components.placeholders import apply_matches
from backend.ocr_settings import OcrSettings

logger = logging.getLogger("uvicorn.error")

ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


class ImageSanitizerError(RuntimeError):
    """Error that is safe to report to the caller without leaking content."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.public_message = message
        self.status_code = status_code


@dataclass
class ImageSanitizeResult:
    """Result of one image sanitization request."""

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


def _decode_base64(value: str, max_bytes: int) -> bytes:
    raw = value.strip()
    if raw.startswith("data:"):
        try:
            _, raw = raw.split(",", 1)
        except ValueError as exc:
            raise ImageSanitizerError("Ungültige Data-URI", 400) from exc
    raw = "".join(raw.split())
    if len(raw) > (max_bytes * 4 // 3) + 1024:
        raise ImageSanitizerError("Bild ist zu groß", 413)
    try:
        data = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ImageSanitizerError("Bild ist kein gültiges Base64", 400) from exc
    if len(data) > max_bytes:
        raise ImageSanitizerError("Bild ist zu groß", 413)
    return data


def decode_image_bytes(data: bytes, settings: OcrSettings) -> Image.Image:
    """Decode and validate an uploaded image without keeping it on disk."""
    if not data:
        raise ImageSanitizerError("Leeres Bild", 400)
    if len(data) > settings.max_bytes:
        raise ImageSanitizerError("Bild ist zu groß", 413)

    previous_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = settings.max_pixels
    try:
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
                image_format = (probe.format or "").upper()
        except Image.DecompressionBombError as exc:
            raise ImageSanitizerError("Bild hat zu viele Pixel", 413) from exc
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageSanitizerError("Bildformat nicht erkannt", 415) from exc
        if image_format not in ALLOWED_FORMATS:
            raise ImageSanitizerError("Nur PNG, JPEG und WebP werden unterstützt", 415)

        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Image.DecompressionBombError as exc:
            raise ImageSanitizerError("Bild hat zu viele Pixel", 413) from exc
        except (UnidentifiedImageError, OSError) as exc:
            raise ImageSanitizerError("Bild konnte nicht gelesen werden", 415) from exc

        if image.width * image.height > settings.max_pixels:
            raise ImageSanitizerError("Bild hat zu viele Pixel", 413)

        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.split()[-1])
            image = background
        else:
            image = image.convert("RGB")
        return image
    finally:
        Image.MAX_IMAGE_PIXELS = previous_limit


def _expand_box(
    box: tuple[int, int, int, int],
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    return (
        max(0, box[0] - padding),
        max(0, box[1] - padding),
        min(width, box[2] + padding),
        min(height, box[3] + padding),
    )


def _line_for_result(result, lines: Iterable[OcrLine]) -> list[OcrLine]:
    return [
        line for line in lines
        if line.end > result.start and line.start < result.end
    ]


def _tokens_for_result(result, lines: Iterable[OcrLine]) -> list[OcrToken]:
    tokens: list[OcrToken] = []
    for line in _line_for_result(result, lines):
        for token in line.tokens:
            if token.end > result.start and token.start < result.end:
                tokens.append(token)
    return tokens


def _redactions_for_results(
    results,
    ocr: OcrResult,
    redaction: str,
    width: int,
    height: int,
    min_confidence: float = 0.0,
) -> tuple[list[dict], list[dict]]:
    padding = max(2, round(min(width, height) * 0.004))
    redactions: dict[tuple[int, int, int, int], dict] = {}
    entities: list[dict] = []

    def add_box(
        box: tuple[int, int, int, int],
        entity_type: str,
        original: str,
    ) -> None:
        expanded = _expand_box(box, width, height, padding)
        entry = redactions.setdefault(expanded, {
            "box": list(expanded),
            "entity_types": [],
            "texts": [],
        })
        if entity_type not in entry["entity_types"]:
            entry["entity_types"].append(entity_type)
        if original not in entry["texts"]:
            entry["texts"].append(original)

    if redaction == "all_text":
        for line in ocr.lines:
            add_box(line.box, "TEXT", line.text)
        return list(redactions.values()), entities

    if min_confidence > 0:
        for line in ocr.lines:
            if line.confidence < min_confidence:
                add_box(line.box, "UNSICHER", line.text)

    for result in results:
        lines = _line_for_result(result, ocr.lines)
        if not lines:
            continue
        if redaction == "line":
            boxes = [line.box for line in lines]
        else:
            tokens = _tokens_for_result(result, lines)
            boxes = [token.box for token in tokens] or [line.box for line in lines]
        boxes = list(dict.fromkeys(boxes))
        original = ocr.text[result.start:result.end]
        for box in boxes:
            add_box(box, result.entity_type, original)
        if boxes:
            entities.append({
                "type": result.entity_type,
                "text": ocr.text[result.start:result.end],
                "score": float(result.score),
                "box": [
                    min(box[0] for box in boxes),
                    min(box[1] for box in boxes),
                    max(box[2] for box in boxes),
                    max(box[3] for box in boxes),
                ],
            })

    ordered = sorted(redactions.values(), key=lambda item: (item["box"][1], item["box"][0]))
    return ordered, entities


def _draw_redactions(image: Image.Image, redactions: list[dict]) -> None:
    draw = ImageDraw.Draw(image)
    for redaction in redactions:
        draw.rectangle(redaction["box"], fill="black")


def _encode_png_base64(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _analysis_text(text: str) -> str:
    """Join OCR lines for NER while keeping character offsets unchanged.

    OCR newlines describe the image layout, not sentence boundaries. Names,
    addresses or IBANs wrapped across lines are otherwise split for the
    analyzer. Replacing one character with another keeps span offsets valid
    for the original text.
    """
    return text.replace("\n", " ")


def _analyze(analyzer: CustomAnalyzer, text: str):
    analyze_text = getattr(analyzer, "analyze_text", None)
    if callable(analyze_text):
        return analyze_text(text)
    results = analyzer.analyzer.analyze(text=text, language=analyzer.language)
    return results, {}


def sanitize_image_bytes(
    data: bytes,
    analyzer: CustomAnalyzer,
    settings: OcrSettings,
    reuse_placeholders: bool = True,
) -> ImageSanitizeResult:
    """OCR an image, mask recognized entities and return a black-boxed PNG."""
    started = time.perf_counter()
    image = decode_image_bytes(data, settings)
    try:
        ocr = run_ocr(image, settings)
    except OcrTimeoutError as exc:
        raise ImageSanitizerError(str(exc), 504) from exc
    except OcrUnavailableError as exc:
        raise ImageSanitizerError(str(exc), 503) from exc
    except OcrError as exc:
        raise ImageSanitizerError(f"OCR fehlgeschlagen: {exc}", 500) from exc
    warnings = list(ocr.warnings)

    if not ocr.text.strip():
        redacted = image.copy()
        return ImageSanitizeResult(
            sanitized_image_base64=_encode_png_base64(redacted),
            sanitized_text="",
            ocr_text="",
            mapping={},
            ocr_engine=ocr.engine,
            ocr_device=ocr.device,
            ocr_confidence=ocr.confidence,
            latency_ms=(time.perf_counter() - started) * 1000,
            image_width=image.width,
            image_height=image.height,
            redactions=[],
            entities=[],
            warnings=warnings,
        )

    results, placeholders = _analyze(analyzer, _analysis_text(ocr.text))
    sanitized_text, mapping = apply_matches(ocr.text, results, placeholders, reuse_placeholders)
    redactions, entities = _redactions_for_results(
        results, ocr, settings.redaction, image.width, image.height, settings.min_confidence
    )
    low_confidence = [
        line for line in ocr.lines if line.confidence < settings.min_confidence
    ]
    if low_confidence:
        warnings.append(
            f"{len(low_confidence)} OCR-Zeile(n) unter der Mindest-Konfidenz wurden geschwärzt."
        )

    redacted = image.copy()
    _draw_redactions(redacted, redactions)

    if settings.verify:
        try:
            verification = run_ocr(redacted, settings)
            if verification.text.strip():
                verify_results, _ = _analyze(analyzer, _analysis_text(verification.text))
                if verify_results:
                    raise ImageSanitizerError(
                        "OCR-Verifikation fehlgeschlagen: nach der Redaktion wurden noch sensible Stellen erkannt",
                        500,
                    )
        except ImageSanitizerError:
            raise
        except Exception as exc:
            raise ImageSanitizerError(
                f"OCR-Verifikation fehlgeschlagen: {exc}", 500
            ) from exc

    return ImageSanitizeResult(
        sanitized_image_base64=_encode_png_base64(redacted),
        sanitized_text=sanitized_text,
        ocr_text=ocr.text,
        mapping=mapping,
        ocr_engine=ocr.engine,
        ocr_device=ocr.device,
        ocr_confidence=ocr.confidence,
        latency_ms=(time.perf_counter() - started) * 1000,
        image_width=image.width,
        image_height=image.height,
        redactions=redactions,
        entities=entities,
        warnings=warnings,
    )


def sanitize_image_base64(
    value: str,
    analyzer: CustomAnalyzer,
    settings: OcrSettings,
    reuse_placeholders: bool = True,
) -> ImageSanitizeResult:
    """Decode a base64/data-URI image and sanitize it."""
    return sanitize_image_bytes(
        _decode_base64(value, settings.max_bytes),
        analyzer,
        settings,
        reuse_placeholders,
    )
