"""
Image sanitizer tests with a fake analyzer/OCR (no Tesseract needed).
Copyright (C) 2026  Christopher Abanilla
"""

import base64
import io

import pytest

pytest.importorskip("PIL")
pytest.importorskip("presidio_analyzer")

from PIL import Image  # noqa: E402

from backend.components import image_sanitizer  # noqa: E402
from backend.components.ocr import OcrLine, OcrResult, OcrToken  # noqa: E402
from backend.ocr_settings import OcrSettings  # noqa: E402


class FakeResult:
    def __init__(self, start, end, entity_type="PERSON", score=0.99):
        self.start = start
        self.end = end
        self.entity_type = entity_type
        self.score = score


class FakeAnalyzer:
    def __init__(self, results=None, placeholders=None):
        self.results = results or []
        self.placeholders = placeholders or {"PERSON": "[NAME]"}
        self.calls = []

    def analyze_text(self, text):
        self.calls.append(text)
        return self.results, self.placeholders


def make_settings(**overrides):
    values = dict(
        enabled=True,
        engine="tesseract",
        device="cpu",
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
    values.update(overrides)
    return OcrSettings(**values)


def png_bytes(width=240, height=80, color="white"):
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def fake_ocr(text="Max Mustermann", box=(10, 10, 210, 40), engine="tesseract"):
    token = OcrToken(text=text, start=0, end=len(text), box=box, confidence=0.9, line_id=0)
    line = OcrLine(
        line_id=0, text=text, start=0, end=len(text), box=box,
        confidence=0.9, tokens=[token],
    )
    return OcrResult(
        text=text, lines=[line], engine=engine, device="cpu",
        confidence=0.9, duration_ms=1.0, warnings=[],
    )


def test_line_redaction_draws_black_box_and_returns_mapping(monkeypatch):
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: fake_ocr())
    analyzer = FakeAnalyzer([FakeResult(0, len("Max Mustermann"))])

    result = image_sanitizer.sanitize_image_bytes(
        png_bytes(), analyzer, make_settings(redaction="line")
    )

    assert result.sanitized_text == "[NAME_1]"
    assert result.mapping == {"[NAME_1]": "Max Mustermann"}
    assert result.redactions and result.entities
    assert result.redactions[0]["box"] == [8, 8, 212, 42]

    redacted = Image.open(io.BytesIO(base64.b64decode(result.sanitized_image_base64)))
    assert redacted.getpixel((10, 10)) == (0, 0, 0)
    assert redacted.getpixel((5, 5)) == (255, 255, 255)


def test_entity_mode_redacts_only_the_recognized_token(monkeypatch):
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: fake_ocr())
    analyzer = FakeAnalyzer([FakeResult(0, 3)])

    result = image_sanitizer.sanitize_image_bytes(
        png_bytes(), analyzer, make_settings(redaction="entity")
    )

    assert result.sanitized_text == "[NAME_1] Mustermann"
    assert result.redactions[0]["box"] == [8, 8, 212, 42]


def test_all_text_redacts_every_ocr_line(monkeypatch):
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: fake_ocr())
    analyzer = FakeAnalyzer([])

    result = image_sanitizer.sanitize_image_bytes(
        png_bytes(), analyzer, make_settings(redaction="all_text")
    )

    assert result.sanitized_text == "Max Mustermann"
    assert result.redactions[0]["entity_types"] == ["TEXT"]


def test_low_confidence_line_is_conservatively_redacted(monkeypatch):
    low = fake_ocr()
    low.lines[0].confidence = 0.2
    low.lines[0].tokens = [
        OcrToken(
            text=t.text, start=t.start, end=t.end, box=t.box,
            confidence=0.2, line_id=t.line_id,
        )
        for t in low.lines[0].tokens
    ]
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: low)
    analyzer = FakeAnalyzer([])

    result = image_sanitizer.sanitize_image_bytes(
        png_bytes(), analyzer, make_settings(min_confidence=0.5)
    )

    assert result.redactions[0]["entity_types"] == ["UNSICHER"]
    assert result.warnings


def test_no_text_returns_an_unmodified_image(monkeypatch):
    monkeypatch.setattr(
        image_sanitizer, "run_ocr",
        lambda image, settings: OcrResult("", [], "tesseract", "cpu", 0.0, 1.0, []),
    )
    analyzer = FakeAnalyzer([])

    result = image_sanitizer.sanitize_image_bytes(png_bytes(), analyzer, make_settings())

    assert result.ocr_text == ""
    assert result.sanitized_text == ""
    assert result.redactions == []
    assert result.mapping == {}


def test_verification_failure_is_fail_closed(monkeypatch):
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: fake_ocr())
    analyzer = FakeAnalyzer([FakeResult(0, len("Max Mustermann"))])

    with pytest.raises(image_sanitizer.ImageSanitizerError):
        image_sanitizer.sanitize_image_bytes(
            png_bytes(), analyzer, make_settings(verify=True)
        )


def test_base64_data_uri_is_accepted(monkeypatch):
    monkeypatch.setattr(image_sanitizer, "run_ocr", lambda image, settings: fake_ocr())
    analyzer = FakeAnalyzer([FakeResult(0, len("Max Mustermann"))])
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes()).decode("ascii")

    result = image_sanitizer.sanitize_image_base64(data_uri, analyzer, make_settings())

    assert result.mapping == {"[NAME_1]": "Max Mustermann"}


def test_invalid_base64_and_oversized_pixels_are_rejected():
    with pytest.raises(image_sanitizer.ImageSanitizerError):
        image_sanitizer.decode_image_bytes(b"not an image", make_settings())

    with pytest.raises(image_sanitizer.ImageSanitizerError):
        image_sanitizer.decode_image_bytes(
            png_bytes(300, 300), make_settings(max_pixels=1000)
        )
