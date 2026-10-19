"""
Tests for the ready-to-use OpenWebUI filter (text + images).
Copyright (C) 2026  Christopher Abanilla
"""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("requests")
pytest.importorskip("pydantic")

_PATH = (
    Path(__file__).resolve().parent.parent
    / "integrations"
    / "openwebui"
    / "entityguard_filter.py"
)
_SPEC = importlib.util.spec_from_file_location("entityguard_filter", _PATH)
filter_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(filter_module)


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def test_block_mode_rejects_images_without_calling_the_service():
    messages = [{
        "role": "user",
        "content": [{
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,AAAA"},
        }],
    }]

    with pytest.raises(ValueError):
        filter_module.mask_messages(
            messages, "http://example/api/v1/sanitize", image_mode="block"
        )


def test_remote_image_urls_are_rejected():
    messages = [{
        "role": "user",
        "content": [{
            "type": "image_url",
            "image_url": {"url": "https://example.test/secret.png"},
        }],
    }]

    with pytest.raises(ValueError):
        filter_module.mask_messages(
            messages, "http://example/api/v1/sanitize", image_mode="redact"
        )


def test_text_is_masked_and_image_is_replaced(monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json))
        if "text" in (json or {}):
            return FakeResponse({"sanitized_text": json["text"], "mapping": {"[NAME_1]": "Max"}})
        return FakeResponse({"sanitized_image_base64": "REDACTED"})

    monkeypatch.setattr(filter_module.requests, "post", fake_post)

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "Hallo Max"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
    }]

    mapping = filter_module.mask_messages(
        messages,
        "http://example/api/v1/sanitize",
        "eg_test",
        image_api_url="http://example/api/v1/sanitize/image",
        image_mode="redact",
    )

    assert messages[0]["content"][0]["text"] == "Hallo Max"
    assert messages[0]["content"][1]["image_url"]["url"] == "data:image/png;base64,REDACTED"
    assert mapping == {"[NAME_1]": "Max"}
    assert calls[0][0].endswith("/api/v1/sanitize")
    assert calls[1][0].endswith("/api/v1/sanitize/image")
    assert calls[1][1]["image_base64"] == "AAAA"


def test_default_image_url_points_to_the_image_endpoint():
    assert filter_module.Filter().valves.image_api_url.endswith("/api/v1/sanitize/image")
