"""
Deactivate the bert_ner recognizer by default.
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
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    """Set bert_ner to inactive by default.

    Migration 007 seeded the bert_ner row active, back when the recognizer
    loaded the xlm-roberta-large model (~2.2 GB). The default model is now
    the much smaller fhswf/bert_de_ner (~440 MB, ~89ms/call on CPU), but the
    recognizer still ships disabled: spaCy + DB patterns alone already
    cover the core entities at ~6ms/call, and BERT is an opt-in quality
    boost for difficult free-text (measured: 65% -> 87% entity recall on
    the benchmark set). Enable it in the admin UI (recognizer edit form)
    followed by /reload - no restart needed. The downgrade restores the
    original active state.
    """
    op.execute("UPDATE recognizers SET is_active = 0 WHERE name = 'bert_ner'")


def downgrade():
    """Restore the active state seeded by migration 007."""
    op.execute("UPDATE recognizers SET is_active = 1 WHERE name = 'bert_ner'")