"""
Detection sources: default IBAN pattern, move date pattern, drop FALLNUMMER.
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

from alembic import op

# revision identifiers, used by Alembic
revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None

# German IBAN: DE + 2 digits + 4x4 digits + 2 digits, optional spaces.
IBAN_REGEX = r"\bDE\d{2}(?:\s?\d{4}){4}\s?\d{2}\b"
# Date TT.MM.JJJJ (moved from MEDICAL_CONTEXT to DATE_TIME).
DATE_REGEX = r"\d{1,2}\.\d{1,2}\.\d{2,4}"


def upgrade():
    """Give every seed entity a real detection source.

    After migration 013 the entities DATE_TIME, IBAN_CODE and FALLNUMMER had
    neither patterns nor a built-in engine (German spaCy NER only emits
    PER/LOC/ORG, and Presidio's Date/Iban recognizers are removed at
    startup). This migration:

    * seeds a default IBAN pattern on IBAN_CODE,
    * moves the date pattern from MEDICAL_CONTEXT to DATE_TIME (renamed
      `datum_generic`, score 0.6) so dates are masked as [DATUM/ZEIT],
    * drops the FALLNUMMER entity - it was never detected; case numbers keep
      being caught by MEDICAL_CONTEXT's `fallnummer_generic`.
    """
    # 1. Default IBAN pattern (idempotent by name)
    op.execute(f"""
        INSERT INTO patterns (name, regex, keywords, score, entity_id, created_at, updated_at)
        SELECT 'iban_de', '{IBAN_REGEX}', NULL, 0.85, e.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM entities e
        WHERE e.name = 'IBAN_CODE'
          AND NOT EXISTS (SELECT 1 FROM patterns WHERE name = 'iban_de')
    """)

    # 2. Move the date pattern to DATE_TIME, rename, raise score
    op.execute(f"""
        UPDATE patterns
        SET name = 'datum_generic',
            entity_id = (SELECT id FROM entities WHERE name = 'DATE_TIME'),
            score = 0.6,
            regex = '{DATE_REGEX}',
            updated_at = CURRENT_TIMESTAMP
        WHERE name = 'geburtsdatum_generic'
    """)

    # 3. Remove the never-detected FALLNUMMER entity
    op.execute("DELETE FROM entities WHERE name = 'FALLNUMMER'")


def downgrade():
    """Reverse: drop IBAN pattern, move date back, restore FALLNUMMER."""
    op.execute("DELETE FROM patterns WHERE name = 'iban_de'")

    op.execute(f"""
        UPDATE patterns
        SET name = 'geburtsdatum_generic',
            entity_id = (SELECT id FROM entities WHERE name = 'MEDICAL_CONTEXT'),
            score = 0.3,
            regex = '{DATE_REGEX}',
            updated_at = CURRENT_TIMESTAMP
        WHERE name = 'datum_generic'
    """)

    op.execute("""
        INSERT INTO entities (name, placeholder, description, is_active, created_at, updated_at)
        VALUES ('FALLNUMMER', '[FALLNUMMER]', 'Medizinische Fallnummern', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO UPDATE SET placeholder = '[FALLNUMMER]', is_active = 1, updated_at = CURRENT_TIMESTAMP
    """)