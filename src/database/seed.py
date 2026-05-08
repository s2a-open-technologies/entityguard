"""
Database seeding module.

This module provides functions to seed the database with initial data
including default entities, recognizers and patterns from the static configuration.
"""

import logging
from sqlalchemy.orm import Session

from .crud import (
    get_recognizers,
    get_entities,
    create_recognizer,
    create_pattern,
    create_context_word,
    create_entity
)

logger = logging.getLogger("uvicorn.error")


def seed_default_entities(db: Session) -> None:
    """
    Seed the database with default entity types.

    Args:
        db: SQLAlchemy database session.
    """
    existing = get_entities(db)
    if existing:
        logger.info("Database already has entities, skipping entity seed")
        return

    logger.info("Seeding database with default entities...")

    default_entities = [
        ("PERSON", "[NAME]", "Person names detected by NLP"),
        ("LOCATION", "[ADRESSE/ORT]", "Addresses and locations"),
        ("DATE_TIME", "[DATUM/ZEIT]", "Dates and times"),
        ("EMAIL_ADDRESS", "[EMAIL]", "Email addresses"),
        ("PHONE_NUMBER", "[TELEFON]", "Phone numbers"),
        ("MEDICAL_CONTEXT", "[MED_IDENTIFIKATOR]", "Medical identifiers (insurance, case numbers, etc.)"),
        ("IBAN_CODE", "[IBAN]", "IBAN bank codes"),
        ("FALLNUMMER", "[FALLNUMMER]", "Medical case numbers"),
    ]

    for name, placeholder, description in default_entities:
        create_entity(db, name=name, placeholder=placeholder, description=description, is_active=True)

    logger.info(f"Seeded {len(default_entities)} default entities")


def seed_default_recognizers(db: Session) -> None:
    """
    Seed the database with default recognizers from the static configuration.

    This function only seeds if the database is empty (no recognizers exist).

    Args:
        db: SQLAlchemy database session.
    """
    # Check if database already has recognizers
    existing = get_recognizers(db)
    if existing:
        logger.info("Database already has recognizers, skipping seed")
        return

    logger.info("Seeding database with default recognizers...")

    # 1. Medical Context Recognizer
    med_recognizer = create_recognizer(
        db,
        name="medizinische_kontexte",
        supported_entity="MEDICAL_CONTEXT",
        supported_language="de",
        is_active=True
    )
    create_pattern(db, name="berufe_exponiert", regex=r"(?i)\b(Bürgermeister|Landrat|Vorstand|Abgeordneter|Chefarzt)\b", score=0.85, recognizer_id=med_recognizer.id)
    create_pattern(db, name="gewerkschaft_de", regex=r"(?i)\b(ver\.di|IG Metall|GEW|Marburger Bund|Gewerkschaft)\b", score=0.95, recognizer_id=med_recognizer.id)
    create_pattern(db, name="krankenkasse_de", regex=r"(?i)\b(AOK|TK|Techniker Krankenkasse|Barmer|DAK|Hallesche|Debeka)\b", score=0.9, recognizer_id=med_recognizer.id)

    # 2. Phone Number Recognizer
    phone_recognizer = create_recognizer(
        db,
        name="telefonnummern_de",
        supported_entity="PHONE_NUMBER",
        supported_language="de",
        is_active=True
    )
    create_pattern(
        db,
        name="telefonnummern_deutschland",
        regex=r"(?:\+49|0|[Oo])(?:\s*\d{2,5}\s*)(?:[/-]?\s*\d{3,9})",
        score=0.85,
        recognizer_id=phone_recognizer.id
    )

    # 3. Email Address Recognizer
    email_recognizer = create_recognizer(
        db,
        name="email_adressen",
        supported_entity="EMAIL_ADDRESS",
        supported_language="de",
        is_active=True
    )
    create_pattern(
        db,
        name="email_regex",
        regex=r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        score=0.95,
        recognizer_id=email_recognizer.id
    )

    # 4. Case Number Recognizer (with context words)
    fall_recognizer = create_recognizer(
        db,
        name="fallnummern_und_daten",
        supported_entity="MEDICAL_CONTEXT",
        supported_language="de",
        is_active=True
    )
    create_pattern(db, name="fallnummer_generic", regex=r"\b\d{5,}\b", score=0.3, recognizer_id=fall_recognizer.id)
    create_pattern(db, name="geburtsdatum_generic", regex=r"\d{1,2}\.\d{1,2}\.\d{2,4}", score=0.3, recognizer_id=fall_recognizer.id)

    # Context words for fall recognizer
    context_words = ["fall", "fallnr", "fallnummer", "fallid", "patient", "patientennummer", "akte", "befund", "aktenzeichen", "az"]
    for word in context_words:
        create_context_word(db, word=word, recognizer_id=fall_recognizer.id)

    logger.info(f"Seeded {4} recognizers with patterns and context words")


def seed_database(db: Session) -> None:
    """
    Seed the database with all default data (entities first, then recognizers).

    Args:
        db: SQLAlchemy database session.
    """
    seed_default_entities(db)
    seed_default_recognizers(db)