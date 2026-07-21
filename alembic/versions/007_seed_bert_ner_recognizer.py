"""
Seed a builtin recognizer row for the BERT NER model, active by default.
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
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    """Seed the 'bert_ner' recognizer row, active by default.

    Unlike the other builtin rows added in 003 (one row per entity type,
    since each maps to a separate underlying Presidio recognizer), the BERT
    NER model is registered as a single recognizer object that detects
    PERSON/LOCATION/ORGANIZATION together, so a single row represents it.
    Its `is_active` flag is read directly by CustomAnalyzer
    (src/components/cstm_analyzer.py) to decide whether to load and
    register the transformer model - toggling it in the admin UI's
    recognizer edit form enables/disables BERT NER without a restart
    (picked up on the next /reload).
    """
    op.execute("""
        INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
        VALUES ('bert_ner', 'PERSON, LOCATION, ORGANIZATION', 'de', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (name) DO UPDATE SET is_builtin = 1, is_active = 1
    """)


def downgrade():
    """Remove the seeded bert_ner recognizer row."""
    op.execute("DELETE FROM recognizers WHERE name = 'bert_ner'")
