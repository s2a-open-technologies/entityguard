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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_password_change: Mapped[datetime] = mapped_column(DateTime, nullable=True)