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
from typing import Optional

import bcrypt
from sqlalchemy.orm import Session

from .models import AdminUser, AllowedValueModel, ContextWordModel, EntityModel, PatternModel, RecognizerModel


def get_recognizer(db: Session, recognizer_id: int) -> Optional[RecognizerModel]:
    """Get a recognizer by ID."""
    return db.query(RecognizerModel).filter(RecognizerModel.id == recognizer_id).first()


def get_recognizer_by_name(db: Session, name: str) -> Optional[RecognizerModel]:
    """Get a recognizer by name."""
    return db.query(RecognizerModel).filter(RecognizerModel.name == name).first()


def get_recognizers(db: Session, skip: int = 0, limit: int = 100, active_only: bool = False) -> list[RecognizerModel]:
    """Get all recognizers, optionally filtering to active only."""
    query = db.query(RecognizerModel)
    if active_only:
        query = query.filter(RecognizerModel.is_active == True)
    return query.offset(skip).limit(limit).all()


def create_recognizer(
    db: Session,
    name: str,
    supported_entity: str,
    supported_language: str = "de",
    is_active: bool = True,
    min_score: Optional[float] = None
) -> RecognizerModel:
    """Create a new recognizer."""
    recognizer = RecognizerModel(
        name=name,
        supported_entity=supported_entity,
        supported_language=supported_language,
        is_active=is_active,
        min_score=min_score
    )
    db.add(recognizer)
    db.commit()
    db.refresh(recognizer)
    return recognizer


def update_recognizer(
    db: Session,
    recognizer_id: int,
    name: Optional[str] = None,
    supported_entity: Optional[str] = None,
    supported_language: Optional[str] = None,
    is_active: Optional[bool] = None,
    min_score: Optional[float] = None,
    clear_min_score: bool = False
) -> Optional[RecognizerModel]:
    """Update a recognizer."""
    recognizer = get_recognizer(db, recognizer_id)
    if not recognizer:
        return None

    if name is not None:
        recognizer.name = name
    if supported_entity is not None:
        recognizer.supported_entity = supported_entity
    if supported_language is not None:
        recognizer.supported_language = supported_language
    if is_active is not None:
        recognizer.is_active = is_active
    if clear_min_score:
        recognizer.min_score = None
    elif min_score is not None:
        recognizer.min_score = min_score

    recognizer.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(recognizer)
    return recognizer


def delete_recognizer(db: Session, recognizer_id: int) -> bool:
    """Delete a recognizer and all its patterns/context words."""
    recognizer = get_recognizer(db, recognizer_id)
    if not recognizer:
        return False

    db.delete(recognizer)
    db.commit()
    return True


# ============================================================================
# Pattern CRUD
# ============================================================================

def get_pattern(db: Session, pattern_id: int) -> Optional[PatternModel]:
    """Get a pattern by ID."""
    return db.query(PatternModel).filter(PatternModel.id == pattern_id).first()


def get_pattern_by_name(db: Session, name: str) -> Optional[PatternModel]:
    """Get a pattern by name."""
    return db.query(PatternModel).filter(PatternModel.name == name).first()


def get_patterns_by_recognizer(db: Session, recognizer_id: int) -> list[PatternModel]:
    """Get all patterns for a recognizer."""
    return db.query(PatternModel).filter(PatternModel.recognizer_id == recognizer_id).all()


def create_pattern(
    db: Session,
    name: str,
    regex: str,
    score: float,
    recognizer_id: int
) -> PatternModel:
    """Create a new pattern."""
    pattern = PatternModel(
        name=name,
        regex=regex,
        score=score,
        recognizer_id=recognizer_id
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


def update_pattern(
    db: Session,
    pattern_id: int,
    name: Optional[str] = None,
    regex: Optional[str] = None,
    score: Optional[float] = None
) -> Optional[PatternModel]:
    """Update a pattern."""
    pattern = get_pattern(db, pattern_id)
    if not pattern:
        return None

    if name is not None:
        pattern.name = name
    if regex is not None:
        pattern.regex = regex
    if score is not None:
        pattern.score = score

    pattern.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pattern)
    return pattern


def delete_pattern(db: Session, pattern_id: int) -> bool:
    """Delete a pattern."""
    pattern = get_pattern(db, pattern_id)
    if not pattern:
        return False

    db.delete(pattern)
    db.commit()
    return True


# ============================================================================
# Context Word CRUD
# ============================================================================

def get_context_word(db: Session, context_word_id: int) -> Optional[ContextWordModel]:
    """Get a context word by ID."""
    return db.query(ContextWordModel).filter(ContextWordModel.id == context_word_id).first()


def get_context_words_by_recognizer(db: Session, recognizer_id: int) -> list[ContextWordModel]:
    """Get all context words for a recognizer."""
    return db.query(ContextWordModel).filter(ContextWordModel.recognizer_id == recognizer_id).all()


def create_context_word(db: Session, word: str, recognizer_id: int) -> ContextWordModel:
    """Create a new context word."""
    context_word = ContextWordModel(word=word, recognizer_id=recognizer_id)
    db.add(context_word)
    db.commit()
    db.refresh(context_word)
    return context_word


def delete_context_word(db: Session, context_word_id: int) -> bool:
    """Delete a context word."""
    context_word = get_context_word(db, context_word_id)
    if not context_word:
        return False

    db.delete(context_word)
    db.commit()
    return True


# ============================================================================
# Admin User CRUD
# ============================================================================

def get_admin_user(db: Session, user_id: int) -> Optional[AdminUser]:
    """Get an admin user by ID."""
    return db.query(AdminUser).filter(AdminUser.id == user_id).first()


def get_admin_user_by_username(db: Session, username: str) -> Optional[AdminUser]:
    """Get an admin user by username."""
    return db.query(AdminUser).filter(AdminUser.username == username).first()


def create_admin_user(db: Session, username: str, password: str) -> AdminUser:
    """Create a new admin user with hashed password."""
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user = AdminUser(username=username, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_admin_password(db: Session, user_id: int, new_password: str) -> Optional[AdminUser]:
    """Update an admin user's password."""
    user = get_admin_user(db, user_id)
    if not user:
        return None

    user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    user.last_password_change = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def authenticate_admin_user(db: Session, username: str, password: str) -> Optional[AdminUser]:
    """Authenticate an admin user by username and password."""
    user = get_admin_user_by_username(db, username)
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# ============================================================================
# Entity CRUD
# ============================================================================

def get_entity(db: Session, entity_id: int) -> Optional[EntityModel]:
    """Get an entity by ID."""
    return db.query(EntityModel).filter(EntityModel.id == entity_id).first()


def get_entity_by_name(db: Session, name: str) -> Optional[EntityModel]:
    """Get an entity by name."""
    return db.query(EntityModel).filter(EntityModel.name == name).first()


def get_entities(db: Session, active_only: bool = False) -> list[EntityModel]:
    """Get all entities, optionally filtering to active only."""
    query = db.query(EntityModel)
    if active_only:
        query = query.filter(EntityModel.is_active.is_(True))
    return query.all()


def create_entity(
    db: Session,
    name: str,
    placeholder: str,
    description: Optional[str] = None,
    is_active: bool = True
) -> EntityModel:
    """Create a new entity."""
    entity = EntityModel(
        name=name,
        placeholder=placeholder,
        description=description,
        is_active=is_active
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def update_entity(
    db: Session,
    entity_id: int,
    name: Optional[str] = None,
    placeholder: Optional[str] = None,
    description: Optional[str] = None,
    is_active: Optional[bool] = None
) -> Optional[EntityModel]:
    """Update an entity."""
    entity = get_entity(db, entity_id)
    if not entity:
        return None

    if name is not None:
        entity.name = name
    if placeholder is not None:
        entity.placeholder = placeholder
    if description is not None:
        entity.description = description
    if is_active is not None:
        entity.is_active = is_active

    entity.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entity)
    return entity


def delete_entity(db: Session, entity_id: int) -> bool:
    """Delete an entity."""
    entity = get_entity(db, entity_id)
    if not entity:
        return False

    db.delete(entity)
    db.commit()
    return True


# ============================================================================
# Allow-List CRUD
# ============================================================================

def get_allowed_value(db: Session, allowed_value_id: int) -> Optional[AllowedValueModel]:
    """Get an allow-listed value by ID."""
    return db.query(AllowedValueModel).filter(AllowedValueModel.id == allowed_value_id).first()


def get_allowed_values(db: Session) -> list[AllowedValueModel]:
    """Get all allow-listed values."""
    return db.query(AllowedValueModel).all()


def get_allowed_value_by_value(db: Session, value: str) -> Optional[AllowedValueModel]:
    """Get an allow-listed value by its exact string."""
    return db.query(AllowedValueModel).filter(AllowedValueModel.value == value).first()


def create_allowed_value(
    db: Session,
    value: str,
    description: Optional[str] = None
) -> AllowedValueModel:
    """Create a new allow-listed value."""
    allowed_value = AllowedValueModel(value=value, description=description)
    db.add(allowed_value)
    db.commit()
    db.refresh(allowed_value)
    return allowed_value


def delete_allowed_value(db: Session, allowed_value_id: int) -> bool:
    """Delete an allow-listed value."""
    allowed_value = get_allowed_value(db, allowed_value_id)
    if not allowed_value:
        return False

    db.delete(allowed_value)
    db.commit()
    return True