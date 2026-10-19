"""
Unit tests for OCR engine selection/fallback.
Copyright (C) 2026  Christopher Abanilla
"""

from backend.components import ocr
from backend.ocr_settings import OcrSettings


def make_settings(engine="auto", device="auto"):
    return OcrSettings(
        enabled=True,
        engine=engine,
        device=device,
        lang="deu+eng",
        redaction="line",
        min_confidence=0.5,
        verify=False,
        max_bytes=1024 * 1024,
        max_pixels=1_000_000,
        timeout_seconds=10,
        tesseract_cmd=None,
        env_overrides=frozenset(),
        warnings=(),
    )


def test_auto_prefers_rapidocr_when_cuda_is_available(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: True)

    assert ocr._choose_engine(make_settings())[:2] == ("rapidocr", "cuda")


def test_auto_uses_tesseract_without_cuda(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    assert ocr._choose_engine(make_settings())[:2] == ("tesseract", "cpu")


def test_requested_rapidocr_gpu_falls_back_to_tesseract(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: True)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    engine, device, warnings = ocr._choose_engine(make_settings("rapidocr", "cuda"))

    assert (engine, device) == ("tesseract", "cpu")
    assert any("CUDA" in warning for warning in warnings)


def test_requested_rapidocr_without_cuda_and_without_tesseract_stays_on_cpu(monkeypatch):
    monkeypatch.setattr(ocr, "tesseract_available", lambda settings: False)
    monkeypatch.setattr(ocr, "rapidocr_available", lambda: True)
    monkeypatch.setattr(ocr, "_cuda_available", lambda: False)

    engine, device, warnings = ocr._choose_engine(make_settings("rapidocr", "cuda"))

    assert (engine, device) == ("rapidocr", "cpu")
    assert any("CUDA" in warning for warning in warnings)
