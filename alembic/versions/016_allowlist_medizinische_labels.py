"""
Allow-list medical label words that the German spaCy NER misclassifies.
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
revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None

# Medical/document label words the German spaCy NER tags as a name or place
# when they stand alone (verified against de_core_news_lg):
#   Fallnr -> PER, Fallnummer/Fallid -> LOC, Fallnummern/Patientennummer -> PER,
#   Az -> LOC.
# They are field labels, not PII, but without this they get masked as
# [NAME]/[ADRESSE/ORT] and can, in running text, even swallow a following
# name ("Max Mustermann Fallnr" -> the NER span). Presidio's allow_list only
# excludes *exact* matches of a recognised span, so these entries are safe:
# the real value ("48291") is still caught by MEDICAL_CONTEXT's
# `fallnummer_generic`, whose context words already include fallnr/fallnummer.
LABELS = [
    ('Fallnr', 'Feldbezeichnung "Fallnummer" - spaCy tagt sie als Person'),
    ('Fallnummer', 'Feldbezeichnung "Fallnummer" - spaCy tagt sie als Ort'),
    ('Fallnummern', 'Plural von "Fallnummer" - spaCy tagt sie als Person'),
    ('Fallid', 'Feldbezeichnung "Fall-ID" - spaCy tagt sie als Ort'),
    ('Patientennummer', 'Feldbezeichnung "Patientennummer" - spaCy tagt sie als Person'),
    ('Az', 'Feldbezeichnung "Aktenzeichen" - spaCy tagt sie als Ort'),
]


def upgrade():
    """Seed the misclassified medical label words into the allow-list (idempotent)."""
    for value, description in LABELS:
        op.execute(f"""
            INSERT INTO allowed_values (value, description, created_at)
            SELECT '{value}', '{description}', CURRENT_TIMESTAMP
            WHERE NOT EXISTS (SELECT 1 FROM allowed_values WHERE value = '{value}')
        """)


def downgrade():
    """Remove only the label words seeded here (user-added entries are kept)."""
    values = ", ".join(f"'{v}'" for v, _ in LABELS)
    op.execute(f"DELETE FROM allowed_values WHERE value IN ({values})")
