"""
Add OpenMed PII model size variants (base 184M, large 434M).
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
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None

# Registry keys from backend.components.bert_recognizer.BERT_MODEL_REGISTRY;
# the row name is the contract between the DB and the code - renaming it
# here requires updating the registry there.
SMALL_SRC_ROW = "transformer_pii_openmed"          # legacy name (44M)
SMALL_ROW = "transformer_pii_openmed_small"        # new consistent name
BASE_ROW = "transformer_pii_openmed_base"          # 184M
LARGE_ROW = "transformer_pii_openmed_large"        # 434M

# Same label scheme for all OpenMed PII German sizes.
SUPPORTED_ENTITY = "PERSON, LOCATION, DATE_TIME, EMAIL_ADDRESS, PHONE_NUMBER, IBAN_CODE"


def upgrade():
    """Rename the 44M row and seed the 184M/434M variants (inactive).

    The three OpenMed PII German models share one label scheme and one
    detector row per size lets the admin pick the accuracy/speed trade-off
    on /admin/modelle. Base and large are marked "GPU empfohlen" in the UI;
    they still work on CPU, just slowly (see scripts/benchmark_all_models.py).
    """
    op.execute(f"""
        UPDATE recognizers
        SET name = '{SMALL_ROW}', updated_at = CURRENT_TIMESTAMP
        WHERE name = '{SMALL_SRC_ROW}'
    """)

    for row in (BASE_ROW, LARGE_ROW):
        op.execute(f"""
            INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
            VALUES ('{row}', '{SUPPORTED_ENTITY}', 'de', 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO NOTHING
        """)


def downgrade():
    """Drop the size variants and restore the legacy row name."""
    for row in (BASE_ROW, LARGE_ROW):
        op.execute(f"DELETE FROM recognizers WHERE name = '{row}'")
    op.execute(f"""
        UPDATE recognizers
        SET name = '{SMALL_SRC_ROW}', updated_at = CURRENT_TIMESTAMP
        WHERE name = '{SMALL_ROW}'
    """)