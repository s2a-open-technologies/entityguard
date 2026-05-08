"""Seed initial recognizers from cstm_patterns

Revision ID: 002
Revises: 001
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '002'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade():
    """Seed initial recognizers and entities from cstm_patterns."""

    # Insert entities with their placeholders
    entities = [
        ('PERSON', '[NAME]', 'Personennamen'),
        ('LOCATION', '[ADRESSE/ORT]', 'Orte und Adressen'),
        ('DATE_TIME', '[DATUM/ZEIT]', 'Datums- und Zeitangaben'),
        ('EMAIL_ADDRESS', '[EMAIL]', 'E-Mail-Adressen'),
        ('PHONE_NUMBER', '[TELEFON]', 'Telefonnummern'),
        ('MEDICAL_CONTEXT', '[MED_IDENTIFIKATOR]', 'Medizinische Kontexte'),
        ('IBAN_CODE', '[SENSITIV]', 'IBAN-Codes'),
    ]

    for name, placeholder, description in entities:
        op.execute(f"""
            INSERT INTO entities (name, placeholder, description, is_active, created_at, updated_at)
            VALUES ('{name}', '{placeholder}', '{description}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET placeholder = '{placeholder}', is_active = 1, updated_at = CURRENT_TIMESTAMP
        """)

    # Insert recognizers - use raw SQL with SQLite
    recognizers = [
        ("medizinische_kontexte", "MEDICAL_CONTEXT", "de", 1),
        ("telefonnummern_de", "PHONE_NUMBER", "de", 1),
        ("email_adressen", "EMAIL_ADDRESS", "de", 1),
        ("fallnummern_und_daten", "MEDICAL_CONTEXT", "de", 1),
    ]

    for name, entity, lang, is_active in recognizers:
        op.execute(f"""
            INSERT INTO recognizers (name, supported_entity, supported_language, is_active, created_at, updated_at)
            VALUES ('{name}', '{entity}', '{lang}', {is_active}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)

    # Insert patterns - using raw SQL with last_insert_rowid logic
    # Note: In a real scenario we'd use RETURNING, but SQLite doesn't support it well in Alembic
    # For simplicity, we'll use a separate SELECT to get the IDs

    # medizinische_kontexte patterns
    med_id = "SELECT id FROM recognizers WHERE name = 'medizinische_kontexte'"
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('berufe_exponiert', '(?i)\\b(Bürgermeister|Landrat|Vorstand|Abgeordneter|Chefarzt)\\b', 0.85, ({med_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('gewerkschaft_de', '(?i)\\b(ver\\.di|IG Metall|GEW|Marburger Bund|Gewerkschaft)\\b', 0.95, ({med_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('krankenkasse_de', '(?i)\\b(AOK|TK|Techniker Krankenkasse|Barmer|DAK|Hallesche|Debeka)\\b', 0.9, ({med_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    # telefonnummern_de patterns
    phone_id = "SELECT id FROM recognizers WHERE name = 'telefonnummern_de'"
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('telefonnummern_deutschland', '(?:\\+49|0|[Oo])(?:\\s*\\d{'{'}2,5{'}'}\\s*)(?:[/-]?\\s*\\d{'{'}3,9{'}'})', 0.85, ({phone_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    # email_adressen patterns
    email_id = "SELECT id FROM recognizers WHERE name = 'email_adressen'"
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('email_regex', '[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+', 0.95, ({email_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    # fallnummern_und_daten patterns
    fall_id = "SELECT id FROM recognizers WHERE name = 'fallnummern_und_daten'"
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('fallnummer_generic', '\\b\\d{'{'}5,{'}'}\\b', 0.3, ({fall_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)
    op.execute(f"""
        INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
        VALUES ('geburtsdatum_generic', '\\d{'{'}1,2{'}'}\\.\\d{'{'}1,2{'}'}\\.\\d{'{'}2,4{'}'}', 0.3, ({fall_id}), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    # Insert context words for fallnummern_und_daten
    fall_context_words = [
        'fall', 'fallnr', 'fallnummer', 'fallid', 'patient',
        'patientennummer', 'akte', 'befund', 'aktenzeichen', 'az'
    ]
    for word in fall_context_words:
        op.execute(f"""
            INSERT INTO context_words (word, recognizer_id, created_at)
            VALUES ('{word}', ({fall_id}), CURRENT_TIMESTAMP)
        """)


def downgrade():
    """Remove seeded recognizers and entities."""
    # Delete recognizers (cascade deletes patterns and context_words)
    recognizer_names = [
        'medizinische_kontexte', 'telefonnummern_de',
        'email_adressen', 'fallnummern_und_daten'
    ]
    for name in recognizer_names:
        op.execute(f"DELETE FROM recognizers WHERE name = '{name}'")

    # Delete entities
    entity_names = [
        'PERSON', 'LOCATION', 'DATE_TIME', 'EMAIL_ADDRESS',
        'PHONE_NUMBER', 'MEDICAL_CONTEXT', 'IBAN_CODE'
    ]
    for name in entity_names:
        op.execute(f"DELETE FROM entities WHERE name = '{name}'")
