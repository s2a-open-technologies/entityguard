"""
Transformer model selection: rename bert_ner, add OpenMed PII model row.
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
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None

# Registry keys from backend.components.bert_recognizer.BERT_MODEL_REGISTRY;
# the row name is the contract between the DB and the code - renaming it
# here requires updating the registry there.
FHSWF_ROW = "transformer_ner_fhswf"
OPENMED_ROW = "transformer_pii_openmed"


def upgrade():
    """Make transformer models selectable via separate recognizer rows.

    1. Rename the legacy 'bert_ner' row (fhswf model) to
       'transformer_ner_fhswf' so its name matches the code registry.
    2. Seed an inactive 'transformer_pii_openmed' row for the OpenMed
       PII model - the admin can enable it like any other recognizer.
    3. Seed the ORGANIZATION entity (placeholder [ORGANISATION]): both
       models detect organizations, but without an active entity the
       ORG/ORGANIZATION hits were silently discarded by process_text.
    """
    # 1. Rename legacy row (keep is_active/is_builtin as-is)
    op.execute(f"""
        UPDATE recognizers
        SET name = '{FHSWF_ROW}', updated_at = CURRENT_TIMESTAMP
        WHERE name = 'bert_ner'
    """)

    # 2. Seed OpenMed row (idempotent, inactive by default like fhswf)
    op.execute(f"""
        INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
        VALUES ('{OPENMED_ROW}', 'PERSON, LOCATION, DATE_TIME, EMAIL_ADDRESS, PHONE_NUMBER, IBAN_CODE', 'de', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO NOTHING
    """)

    # 3. Seed ORGANIZATION entity so ORG hits are actually masked
    op.execute("""
        INSERT INTO entities (name, placeholder, description, is_active, created_at, updated_at)
        VALUES ('ORGANIZATION', '[ORGANISATION]', 'Firmen, Kliniken, Behörden und andere Organisationen (transformer-Modelle)', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO UPDATE SET placeholder = '[ORGANISATION]', is_active = 1, updated_at = CURRENT_TIMESTAMP
    """)


def downgrade():
    """Undo the rename, drop the OpenMed row and the ORGANIZATION entity."""
    op.execute("DELETE FROM entities WHERE name = 'ORGANIZATION'")
    op.execute(f"DELETE FROM recognizers WHERE name = '{OPENMED_ROW}'")
    op.execute(f"""
        UPDATE recognizers
        SET name = 'bert_ner', updated_at = CURRENT_TIMESTAMP
        WHERE name = '{FHSWF_ROW}'
    """)