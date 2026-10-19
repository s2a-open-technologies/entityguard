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

"""API tests for /api/v1/sanitize with a fake analyzer (needs fastapi + Presidio importable)."""

import inspect

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import backend.views.anonymizer as anonymizer  # noqa: E402
from backend.security import require_api_key  # noqa: E402


class FakeAnalyzer:
    def __init__(self):
        self.calls = []

    def process_text(self, text, db=None, reuse_placeholders=False):
        self.calls.append((text, reuse_placeholders))
        return text.replace("Max", "[NAME_1]"), {"[NAME_1]": "Max"}


@pytest.fixture
def client(monkeypatch):
    fake = FakeAnalyzer()
    monkeypatch.setattr(anonymizer, "_analyzer", fake)
    monkeypatch.setattr(anonymizer, "record_trace", lambda *a, **k: None)
    app = FastAPI()
    app.include_router(anonymizer.entityguard_router)
    app.dependency_overrides[require_api_key] = lambda: {"key_prefix": "eg_test"}
    return TestClient(app), fake


def test_sanitize_returns_text_and_mapping_and_keeps_old_clients_working(client):
    c, fake = client
    r = c.post("/api/v1/sanitize", json={"text": "Hallo Max"})
    assert r.status_code == 200 and r.json() == {"sanitized_text": "Hallo [NAME_1]", "mapping": {"[NAME_1]": "Max"}}
    assert fake.calls == [("Hallo Max", False)]  # default: one placeholder per occurrence


def test_sanitize_passes_the_reuse_flag(client):
    c, fake = client
    c.post("/api/v1/sanitize", json={"text": "Max und Max", "reuse_placeholders": True})
    assert fake.calls == [("Max und Max", True)]


def test_sanitize_is_fail_closed_on_errors(client, monkeypatch):
    c, fake = client
    monkeypatch.setattr(fake, "process_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = c.post("/api/v1/sanitize", json={"text": "Hallo Max"})
    assert r.status_code == 500 and "Hallo Max" not in r.text


def test_endpoints_are_plain_functions_so_they_run_in_the_threadpool():
    # `async def` would run the CPU-bound analysis on the event loop and freeze /health and every other request
    assert not inspect.iscoroutinefunction(anonymizer.sanitize)
    assert not inspect.iscoroutinefunction(anonymizer.sanitize_image)
    assert not inspect.iscoroutinefunction(anonymizer.reload_patterns)


def test_image_endpoint_is_fail_closed_on_invalid_input(client):
    c, _ = client
    r = c.post("/api/v1/sanitize/image", json={"image_base64": "not-base64"})
    assert r.status_code in (400, 413, 415)
    assert "sanitized_image_base64" not in r.text


def test_image_endpoint_is_disabled_with_404(client, monkeypatch):
    from backend.ocr_settings import OcrSettings

    c, _ = client
    monkeypatch.setattr(
        anonymizer, "get_ocr_settings",
        lambda db: OcrSettings(
            enabled=False, engine="auto", device="auto", lang="deu+eng",
            redaction="line", min_confidence=0.5, verify=False,
            max_bytes=1024 * 1024, max_pixels=1_000_000, timeout_seconds=10,
            tesseract_cmd=None, env_overrides=frozenset(), warnings=(),
        ),
    )
    r = c.post("/api/v1/sanitize/image", json={"image_base64": "x"})
    assert r.status_code == 404
