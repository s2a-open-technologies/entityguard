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

"""Tests for API keys supplied via ENTITYGUARD_API_KEY / ENTITYGUARD_API_KEY_FILE."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("bcrypt")

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

import backend.security as security  # noqa: E402
from backend import config  # noqa: E402

ENV_KEY = "env-key-0123456789abcdef"


class _NullSession:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _request(headers: dict) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw})


@pytest.fixture
def no_db_keys(monkeypatch):
    monkeypatch.setattr(security, "SessionLocal", _NullSession)
    monkeypatch.setattr(security, "get_active_api_keys", lambda db: [])


@pytest.mark.parametrize("headers", [
    {"Authorization": f"Bearer {ENV_KEY}"},
    {"X-API-Key": ENV_KEY},
])
def test_env_key_is_accepted_via_both_headers(monkeypatch, no_db_keys, headers):
    monkeypatch.setattr(config, "API_KEYS_FROM_ENV", ["other-key-0123456789", ENV_KEY])
    assert security.require_api_key(_request(headers)) == {"id": None, "name": "ENV", "key_prefix": "env"}


def test_wrong_key_is_rejected_when_env_key_set(monkeypatch, no_db_keys):
    monkeypatch.setattr(config, "API_KEYS_FROM_ENV", [ENV_KEY])
    with pytest.raises(HTTPException) as exc:
        security.require_api_key(_request({"X-API-Key": ENV_KEY + "x"}))
    assert exc.value.status_code == 401 and "invalid" in exc.value.detail


def test_without_env_and_db_keys_api_stays_closed(monkeypatch, no_db_keys):
    monkeypatch.setattr(config, "API_KEYS_FROM_ENV", [])
    with pytest.raises(HTTPException) as exc:
        security.require_api_key(_request({"X-API-Key": ENV_KEY}))
    assert exc.value.status_code == 401 and "no API key configured" in exc.value.detail


def test_env_parsing_combines_list_and_file_and_drops_short_keys(monkeypatch, tmp_path):
    key_file = tmp_path / "secret"
    key_file.write_text("file-key-0123456789abc\n\n" + ENV_KEY + "\n")
    monkeypatch.setenv("ENTITYGUARD_API_KEY", f" {ENV_KEY} , short ,,second-key-0123456789")
    monkeypatch.setenv("ENTITYGUARD_API_KEY_FILE", str(key_file))
    assert config._env_api_keys() == [ENV_KEY, "second-key-0123456789", "file-key-0123456789abc"]


def test_unreadable_key_file_yields_no_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("ENTITYGUARD_API_KEY", raising=False)
    monkeypatch.setenv("ENTITYGUARD_API_KEY_FILE", str(tmp_path / "missing"))
    assert config._env_api_keys() == []
