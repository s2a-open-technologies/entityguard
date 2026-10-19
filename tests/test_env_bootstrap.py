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

"""Tests for the headless startup env vars ENTITYGUARD_ADMIN_PASSWORD and ENTITYGUARD_MODELS."""

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("bcrypt")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from backend import config  # noqa: E402
from backend.database import crud  # noqa: E402
from backend.database.models import AuditLogModel, Base  # noqa: E402

KEYS = ["transformer_ner_fhswf", "transformer_pii_openmed_small",
        "transformer_pii_openmed_base", "transformer_pii_openmed_large"]


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        yield session


def test_env_admin_is_created_then_left_alone(db):
    assert crud.ensure_env_admin(db, "ops", "geheim-12345") == "created"
    user = crud.get_admin_user_by_username(db, "ops")
    assert user.role == "admin" and user.is_active
    assert crud.verify_password("geheim-12345", user.password_hash)
    assert crud.ensure_env_admin(db, "ops", "geheim-12345") is None  # already in sync, no write
    assert db.query(AuditLogModel).count() == 1


def test_env_admin_resets_password_role_and_active_flag(db):
    user = crud.create_admin_user(db, "admin", "admin", role="viewer")
    crud.set_admin_user_active(db, user.id, False)
    assert crud.ensure_env_admin(db, "admin", "neues-passwort") == "updated"
    db.refresh(user)
    assert user.role == "admin" and user.is_active
    assert crud.verify_password("neues-passwort", user.password_hash)
    assert not crud.verify_password("admin", user.password_hash)


def test_admin_password_env_parsing(monkeypatch, tmp_path):
    secret = tmp_path / "pw"
    secret.write_text("aus-datei-123\n")
    monkeypatch.delenv("ENTITYGUARD_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ENTITYGUARD_ADMIN_PASSWORD_FILE", str(secret))
    assert config._env_admin_password() == "aus-datei-123"
    monkeypatch.delenv("ENTITYGUARD_ADMIN_PASSWORD_FILE")
    monkeypatch.setenv("ENTITYGUARD_ADMIN_PASSWORD", "kurz")
    assert config._env_admin_password() is None  # < 8 characters -> ignored


def test_sync_detector_models_sets_exactly_the_requested_models(db):
    crud.set_detector_model_active(db, "transformer_ner_fhswf", True)
    changed = crud.sync_detector_models(db, KEYS, ["transformer_pii_openmed_small"])
    assert sorted(changed) == ["transformer_ner_fhswf", "transformer_pii_openmed_small"]
    active = {r.name for r in crud.get_detector_models(db) if r.is_active}
    assert active == {"transformer_pii_openmed_small"}
    assert crud.sync_detector_models(db, KEYS, ["transformer_pii_openmed_small"]) == []


def test_resolve_model_keys_accepts_full_and_short_names():
    pytest.importorskip("presidio_analyzer")
    from backend.components.bert_recognizer import resolve_model_keys

    assert resolve_model_keys("openmed_small") == (["transformer_pii_openmed_small"], [])
    assert resolve_model_keys(" Transformer_PII_OpenMed_Large , fhswf ") == (
        ["transformer_ner_fhswf", "transformer_pii_openmed_large"], [])
    assert resolve_model_keys("none") == ([], [])
    assert resolve_model_keys("gpt5,openmed_base") == (["transformer_pii_openmed_base"], ["gpt5"])
