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


class RecognizerModel(Base):
    """
    Model for a pattern recognizer.

    A recognizer contains one or more patterns and optionally context words
    for detecting specific entity types in text.

    Attributes:
        id: Primary key
        name: Unique name for the recognizer
        supported_entity: The entity type this recognizer detects (e.g., "MEDICAL_CONTEXT")
        supported_language: Language code (default: "de")
        is_active: Whether this recognizer is currently active
        is_builtin: Whether this is a built-in Presidio recognizer
        min_score: Optional per-recognizer confidence floor (0.0-1.0).
            NULL means the global default_score_threshold applies. Only
            consumed by BertNerRecognizer so far.
        patterns: List of patterns associated with this recognizer
        context_words: List of context words for improved detection
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "recognizers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    supported_entity: Mapped[str] = mapped_column(String(100), nullable=False)
    supported_language: Mapped[str] = mapped_column(String(10), default="de")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    min_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patterns: Mapped[list["PatternModel"]] = relationship(
        "PatternModel", back_populates="recognizer", cascade="all, delete-orphan"
    )
    context_words: Mapped[list["ContextWordModel"]] = relationship(
        "ContextWordModel", back_populates="recognizer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<RecognizerModel(name='{self.name}', entity='{self.supported_entity}')>"


class PatternModel(Base):
    """
    Model for a regex pattern within a recognizer.

    Attributes:
        id: Primary key
        name: Unique name for the pattern
        regex: The regular expression pattern
        score: Confidence score for the pattern (0.0 to 1.0)
        recognizer_id: Foreign key to the parent recognizer
        created_at: Timestamp of creation
        updated_at: Timestamp of last update
    """
    __tablename__ = "patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    regex: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    recognizer_id: Mapped[int] = mapped_column(ForeignKey("recognizers.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recognizer: Mapped["RecognizerModel"] = relationship("RecognizerModel", back_populates="patterns")

    def __repr__(self) -> str:
        return f"<PatternModel(name='{self.name}', score={self.score})>"


class ContextWordModel(Base):
    """
    Model for context words associated with a recognizer.

    Context words help improve detection accuracy by providing
    surrounding context that indicates the entity type.

    Attributes:
        id: Primary key
        word: The context word
        recognizer_id: Foreign key to the parent recognizer
        created_at: Timestamp of creation
    """
    __tablename__ = "context_words"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(100), nullable=False)
    recognizer_id: Mapped[int] = mapped_column(ForeignKey("recognizers.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    recognizer: Mapped["RecognizerModel"] = relationship("RecognizerModel", back_populates="context_words")

    def __repr__(self) -> str:
        return f"<ContextWordModel(word='{self.word}')>"


class EntityModel(Base):
    """
    Model for custom entity types.

    Custom entities can be created by users and selected when creating recognizers.

    Attributes:
        id: Primary key
        name: Unique entity name (e.g., "PATIENT_ID", "MEDICAL_LICENSE")
        description: Optional description of what this entity represents
        placeholder: The placeholder text to use when anonymizing (e.g., "[PATIENT_ID]")
        is_active: Whether this entity is currently active
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

    def __repr__(self) -> str:
        return f"<EntityModel(name='{self.name}', placeholder='{self.placeholder}')>"


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