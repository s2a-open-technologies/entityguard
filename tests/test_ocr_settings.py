"""
Unit tests for OCR settings/env overrides (no OCR engine needed).
Copyright (C) 2026  Christopher Abanilla
"""

import pytest

from backend import ocr_settings


def test_normalize_setting_accepts_valid_values():
    assert ocr_settings.normalize_setting("ocr_engine", "rapidocr") == "rapidocr"
    assert ocr_settings.normalize_setting("ocr_enabled", "YES") == "true"
    assert ocr_settings.normalize_setting("ocr_redaction", "line") == "line"
    assert ocr_settings.normalize_setting("ocr_min_confidence", "0,7") == "0.7"
    assert ocr_settings.normalize_setting("image_max_bytes", "2048") == "2048"


def test_normalize_setting_rejects_invalid_values():
    with pytest.raises(ValueError):
        ocr_settings.normalize_setting("ocr_engine", "magic")
    with pytest.raises(ValueError):
        ocr_settings.normalize_setting("ocr_redaction", "everything")
    with pytest.raises(ValueError):
        ocr_settings.normalize_setting("ocr_min_confidence", "1.5")
    with pytest.raises(ValueError):
        ocr_settings.normalize_setting("image_max_bytes", "10")


def test_environment_overrides_database(monkeypatch):
    monkeypatch.setattr(
        ocr_settings, "get_app_settings",
        lambda db: {"ocr_engine": "tesseract", "ocr_redaction": "entity"},
    )
    monkeypatch.setenv("ENTITYGUARD_OCR_ENGINE", "rapidocr")
    monkeypatch.setenv("ENTITYGUARD_OCR_REDACTION", "all_text")

    settings = ocr_settings.get_ocr_settings(None)

    assert settings.engine == "rapidocr"
    assert settings.redaction == "all_text"
    assert {"ocr_engine", "ocr_redaction"} <= set(settings.env_overrides)


def test_invalid_environment_value_is_ignored_with_warning(monkeypatch):
    monkeypatch.setattr(ocr_settings, "get_app_settings", lambda db: {})
    monkeypatch.setenv("ENTITYGUARD_OCR_MIN_CONFIDENCE", "nope")

    settings = ocr_settings.get_ocr_settings(None)

    assert settings.min_confidence == 0.5
    assert any("ENTITYGUARD_OCR_MIN_CONFIDENCE" in warning for warning in settings.warnings)


def test_env_values_cover_every_environment_variable():
    assert set(ocr_settings.ENV_VALUES) == set(ocr_settings.ENV_NAMES)
    assert ocr_settings.ENV_VALUES["ocr_enabled"] == "on|off"
    assert ocr_settings.ENV_VALUES["ocr_engine"] == "auto|tesseract|rapidocr"
    assert ocr_settings.ENV_DEFAULTS_DISPLAY["ocr_enabled"] == "on"
    assert ocr_settings.ENV_DEFAULTS_DISPLAY["ocr_verify"] == "off"


def test_defaults_are_used_without_database_or_environment(monkeypatch):
    monkeypatch.setattr(ocr_settings, "get_app_settings", lambda db: {})
    for env_name in ocr_settings.ENV_NAMES.values():
        monkeypatch.delenv(env_name, raising=False)

    settings = ocr_settings.get_ocr_settings(None)

    assert settings.enabled is True
    assert settings.engine == "auto"
    assert settings.redaction == "line"
    assert settings.max_bytes == 10485760
