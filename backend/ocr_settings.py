"""
Admin-editable OCR/image settings with environment overrides.
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
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy.orm import Session

from backend.database.crud import get_app_settings, set_app_settings

logger = logging.getLogger("uvicorn.error")

# Environment variables intentionally use the ENTITYGUARD_ prefix so a
# headless container can be configured without touching the admin UI.
ENV_NAMES: dict[str, str] = {
    "ocr_enabled": "ENTITYGUARD_OCR_ENABLED",
    "ocr_engine": "ENTITYGUARD_OCR_ENGINE",
    "ocr_device": "ENTITYGUARD_OCR_DEVICE",
    "ocr_lang": "ENTITYGUARD_OCR_LANG",
    "ocr_redaction": "ENTITYGUARD_OCR_REDACTION",
    "ocr_min_confidence": "ENTITYGUARD_OCR_MIN_CONFIDENCE",
    "ocr_verify": "ENTITYGUARD_OCR_VERIFY",
    "image_max_bytes": "ENTITYGUARD_IMAGE_MAX_BYTES",
    "image_max_pixels": "ENTITYGUARD_IMAGE_MAX_PIXELS",
    "ocr_timeout_seconds": "ENTITYGUARD_OCR_TIMEOUT_SECONDS",
}

DEFAULTS: dict[str, str] = {
    "ocr_enabled": "true",
    "ocr_engine": "auto",
    "ocr_device": "auto",
    "ocr_lang": "deu+eng",
    "ocr_redaction": "line",
    "ocr_min_confidence": "0.5",
    "ocr_verify": "false",
    "image_max_bytes": "10485760",
    "image_max_pixels": "40000000",
    "ocr_timeout_seconds": "30",
}

ENGINES = ("auto", "tesseract", "rapidocr")
DEVICES = ("auto", "cpu", "cuda")
REDACTIONS = ("entity", "line", "all_text")

# Human-readable defaults for the admin env-var reference (bool -> on/off).
ENV_DEFAULTS_DISPLAY: dict[str, str] = {
    key: "on" if value == "true" else "off" if value == "false" else value
    for key, value in DEFAULTS.items()
}

# Human-readable accepted values for the admin env-var reference.
ENV_VALUES: dict[str, str] = {
    "ocr_enabled": "on|off",
    "ocr_engine": "|".join(ENGINES),
    "ocr_device": "|".join(DEVICES),
    "ocr_lang": "deu+eng",
    "ocr_redaction": "|".join(REDACTIONS),
    "ocr_min_confidence": "0.0-1.0",
    "ocr_verify": "on|off",
    "image_max_bytes": "Bytes (>=1024)",
    "image_max_pixels": "Pixel (>=10000)",
    "ocr_timeout_seconds": "Sekunden (>=1)",
}


@dataclass(frozen=True)
class OcrSettings:
    """Resolved OCR settings (DB values, then environment overrides)."""

    enabled: bool
    engine: str
    device: str
    lang: str
    redaction: str
    min_confidence: float
    verify: bool
    max_bytes: int
    max_pixels: int
    timeout_seconds: int
    tesseract_cmd: str | None
    env_overrides: frozenset[str]
    warnings: tuple[str, ...]


def _parse_bool(key: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{key}: erwartet true/false, erhalten: {value!r}")


def _parse_int(key: str, value: str, minimum: int = 0) -> int:
    try:
        parsed = int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{key}: erwartet eine Ganzzahl, erhalten: {value!r}") from exc
    if parsed < minimum:
        raise ValueError(f"{key}: muss >= {minimum} sein")
    return parsed


def _parse_float(key: str, value: str, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value.strip().replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{key}: erwartet eine Zahl, erhalten: {value!r}") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{key}: muss zwischen {minimum} und {maximum} liegen")
    return parsed


def normalize_setting(key: str, value: str) -> str:
    """Validate one setting and return its canonical string representation."""
    if key not in DEFAULTS:
        raise ValueError(f"Unbekannte Einstellung: {key}")
    value = str(value).strip()
    if key in ("ocr_enabled", "ocr_verify"):
        return "true" if _parse_bool(key, value) else "false"
    if key == "ocr_engine":
        if value not in ENGINES:
            raise ValueError(f"ocr_engine: erwartet {', '.join(ENGINES)}")
        return value
    if key == "ocr_device":
        if value not in DEVICES:
            raise ValueError(f"ocr_device: erwartet {', '.join(DEVICES)}")
        return value
    if key == "ocr_redaction":
        if value not in REDACTIONS:
            raise ValueError(f"ocr_redaction: erwartet {', '.join(REDACTIONS)}")
        return value
    if key == "ocr_lang":
        if not value or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789+_-" for ch in value.lower()):
            raise ValueError("ocr_lang: erwartet z. B. 'deu+eng'")
        return value.lower()
    if key == "ocr_min_confidence":
        return f"{_parse_float(key, value):g}"
    if key == "image_max_bytes":
        return str(_parse_int(key, value, minimum=1024))
    if key == "image_max_pixels":
        return str(_parse_int(key, value, minimum=10000))
    if key == "ocr_timeout_seconds":
        return str(_parse_int(key, value, minimum=1))
    return value


def validate_settings(values: Mapping[str, str]) -> dict[str, str]:
    """Validate a partial settings mapping; returns canonical values."""
    return {key: normalize_setting(key, value) for key, value in values.items()}


def environment_values() -> dict[str, str]:
    """Return the OCR settings currently supplied via environment variables."""
    return {
        key: value
        for key, env_name in ENV_NAMES.items()
        if (value := os.getenv(env_name)) is not None
    }


def get_ocr_settings(db: Session) -> OcrSettings:
    """Resolve persisted settings, then apply environment overrides."""
    values = dict(DEFAULTS)
    warnings: list[str] = []

    try:
        values.update(get_app_settings(db))
    except Exception as exc:
        logger.warning("Could not read app settings from DB: %s", exc)
        warnings.append("Datenbank-Einstellungen konnten nicht gelesen werden; Defaults aktiv.")

    env_values = environment_values()
    env_overrides: set[str] = set()
    for key, raw in env_values.items():
        try:
            values[key] = normalize_setting(key, raw)
            env_overrides.add(key)
        except ValueError as exc:
            logger.error("Ignoring environment setting %s: %s", ENV_NAMES[key], exc)
            warnings.append(f"{ENV_NAMES[key]} ungültig, ignoriert: {exc}")

    normalized: dict[str, str] = {}
    for key in DEFAULTS:
        try:
            normalized[key] = normalize_setting(key, values.get(key, DEFAULTS[key]))
        except ValueError as exc:
            logger.warning("Invalid persisted setting %s: %s", key, exc)
            warnings.append(f"{key} ungültig, Default aktiv: {exc}")
            normalized[key] = DEFAULTS[key]

    return OcrSettings(
        enabled=normalized["ocr_enabled"] == "true",
        engine=normalized["ocr_engine"],
        device=normalized["ocr_device"],
        lang=normalized["ocr_lang"],
        redaction=normalized["ocr_redaction"],
        min_confidence=float(normalized["ocr_min_confidence"]),
        verify=normalized["ocr_verify"] == "true",
        max_bytes=int(normalized["image_max_bytes"]),
        max_pixels=int(normalized["image_max_pixels"]),
        timeout_seconds=int(normalized["ocr_timeout_seconds"]),
        tesseract_cmd=os.getenv("ENTITYGUARD_TESSERACT_CMD") or None,
        env_overrides=frozenset(env_overrides),
        warnings=tuple(warnings),
    )


def save_ocr_settings(db: Session, values: Mapping[str, str]) -> dict[str, str]:
    """Validate and persist OCR settings. Raises ValueError on invalid input."""
    normalized = validate_settings(values)
    set_app_settings(db, normalized)
    return normalized


def settings_for_admin(db: Session) -> tuple[dict[str, str], frozenset[str]]:
    """Return the effective values and which keys are environment-locked."""
    values = dict(DEFAULTS)
    try:
        values.update(get_app_settings(db))
    except Exception as exc:
        logger.warning("Could not read app settings from DB: %s", exc)
    overrides = environment_values()
    for key, raw in overrides.items():
        try:
            values[key] = normalize_setting(key, raw)
        except ValueError:
            pass
    return values, frozenset(overrides)
