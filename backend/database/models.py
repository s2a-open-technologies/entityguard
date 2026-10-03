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

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class EntityModel(Base):
    """
    Model for an entity type (the central unit of the configuration).

    An entity defines what kind of sensitive data is recognized and how it
    is replaced. Its regex patterns and context words hang directly off the
    entity via `entity_id`; the old intermediate "recognizer" layer was
    removed in migration 013.

    Attributes:
        id: Primary key
        name: Unique entity name (e.g., "PATIENT_ID", "MEDICAL_LICENSE")
        description: Optional description of what this entity represents
        placeholder: The placeholder text to use when anonymizing (e.g., "[PATIENT_ID]")
        is_active: Whether this entity is currently active
        patterns: List of regex patterns for this entity
        context_words: List of context words for improved detection
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholder: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patterns: Mapped[list["PatternModel"]] = relationship(
        "PatternModel", back_populates="entity", cascade="all, delete-orphan"
    )
    context_words: Mapped[list["ContextWordModel"]] = relationship(
        "ContextWordModel", back_populates="entity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EntityModel(name='{self.name}', placeholder='{self.placeholder}')>"


class DetectorModel(Base):
    """
    Model for a transformer/NER detector model (on/off switch).

    These rows persist the enable state of the models defined in
    `backend/components/bert_recognizer.py` (`BERT_MODEL_REGISTRY`, keyed by
    `name`). They are NOT editable detector rules - model and label mapping
    live in code; the admin UI only flips `is_active`.

    Attributes:
        id: Primary key
        name: Registry key, matches BERT_MODEL_REGISTRY (code contract)
        is_active: Whether the model runs
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "detector_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<DetectorModel(name='{self.name}', active={self.is_active})>"


class PatternModel(Base):
    """
    Model for a regex pattern belonging to an entity.

    `regex` is always a raw Python `re` pattern. Patterns created via the
    admin UI's keyword mode are compiled to a regex there, so the stored
    value can be either hand-written or generated. The optional `keywords`
    list preserves the simple term list for round-tripping the UI.

    Attributes:
        id: Primary key
        name: Unique name for the pattern
        regex: The regular expression pattern
        keywords: Optional keyword list (JSON/CSV) if the pattern was built in keyword mode
        score: Confidence score for the pattern (0.0 to 1.0)
        entity_id: Foreign key to the owning entity
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    regex: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entity: Mapped["EntityModel"] = relationship("EntityModel", back_populates="patterns")

    def __repr__(self) -> str:
        return f"<PatternModel(name='{self.name}', score={self.score})>"


class ContextWordModel(Base):
    """
    Model for a context word belonging to an entity.

    Context words help improve detection accuracy by providing
    surrounding context that indicates the entity type.

    Attributes:
        id: Primary key
        word: The context word
        entity_id: Foreign key to the owning entity
        created_at: Timestamp of creation
    """
    __tablename__ = "context_words"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entity: Mapped["EntityModel"] = relationship("EntityModel", back_populates="context_words")

    def __repr__(self) -> str:
        return f"<ContextWordModel(word='{self.word}')>"


class AllowedValueModel(Base):
    """
    Model for an allow-listed value that is never masked.

    Exact strings here are excluded from sanitization results regardless
    of which recognizer (spaCy, BERT, or a custom pattern) flagged them -
    e.g. a company name that gets falsely detected as a PERSON/ORGANIZATION.

    Attributes:
        id: Primary key
        value: The exact string to never mask
        description: Optional note on why this value is allow-listed
        created_at: Timestamp of creation
    """
    __tablename__ = "allowed_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<AllowedValueModel(value='{self.value}')>"


class ApiKeyModel(Base):
    """
    Model for an API key that grants access to the JSON API.

    Keys are created in the admin UI (label + one-time plaintext display);
    only the bcrypt hash is stored, so a lost key can never be recovered -
    create a new one instead. Multiple keys may share the same label (e.g.
    several devices of one app). The API rejects every request with HTTP 401
    while no active key exists (fail-closed).

    Attributes:
        id: Primary key
        name: Free-text label ("app name"), not unique
        key_prefix: Recognizable prefix of the key for the list view (e.g. "eg_openwebui")
        key_hash: Bcrypt hash of the full key
        is_active: Whether the key is currently accepted
        created_at: Timestamp of creation
        last_used_at: Timestamp of the last successful API call (optional)
    """
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(120), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ApiKeyModel(name='{self.name}', prefix='{self.key_prefix}', active={self.is_active})>"


class AdminUser(Base):
    """
    Model for admin user authentication.

    Attributes:
        id: Primary key
        username: Unique username for login
        password_hash: Bcrypt hashed password
        is_active: Whether this user account is active
        created_at: Timestamp of account creation
        last_password_change: Timestamp of last password change
    """
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="admin", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_password_change: Mapped[datetime] = mapped_column(DateTime, nullable=True)

class AuditLogModel(Base):
    """
    Append-only audit log of configuration changes and login events.

    Records *who* changed *what* (entities, patterns, context words,
    allow-list, API keys, detector models, users) and login successes/
    failures. It never stores the changed values themselves.

    Attributes:
        id: Primary key
        created_at: Timestamp of the event
        actor_id: User ID of the actor (None for failed logins)
        actor_username: Username of the actor (also set for failed logins)
        action: create/update/delete/toggle/login/login_failed/password_change/logout
        target_type: Affected object type (entity, pattern, ...), optional
        target_id: Affected object ID, optional
        target_label: Human-readable label of the target, optional
        summary: Short human-readable description
        ip_address: Client IP, optional
    """
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actor_id: Mapped[int | None] = mapped_column(nullable=True)
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(150), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)


class RequestTraceModel(Base):
    """
    Tracing-lite row for a single sanitize request.

    Deliberately content-free: only metadata about the request (length,
    number of masks, entity-type counts, latency, success) plus an optional
    keyed hash (HMAC) of the input for correlation. It never stores the raw
    text, the masked output or the placeholder->original mapping. Retention
    is bounded by TRACE_RETENTION_DAYS.

    Attributes:
        id: Primary key
        created_at: Timestamp of the request
        api_key_prefix: Display prefix of the key used
        source: Request origin (currently always "api")
        input_length: Character length of the input
        mask_count: Total number of masked entities
        entity_counts: JSON mapping entity type -> count
        latency_ms: Processing time in milliseconds
        success: Whether processing succeeded
        input_hmac: Keyed hash (HMAC-SHA256) of the input, optional
    """
    __tablename__ = "request_trace"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    api_key_prefix: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    input_length: Mapped[int] = mapped_column(nullable=False)
    mask_count: Mapped[int] = mapped_column(nullable=False, default=0)
    entity_counts: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    input_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
