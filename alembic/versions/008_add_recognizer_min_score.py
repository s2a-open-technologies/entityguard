"""
Add a per-recognizer minimum score column.
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
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Add a nullable min_score column to recognizers.

    NULL means "use the global default_score_threshold". Currently only
    read by BertNerRecognizer (src/components/bert_recognizer.py) as a
    per-recognizer confidence floor; not yet consumed by DB-driven
    PatternRecognizers, which already have a per-pattern score instead.
    """
    op.add_column('recognizers', sa.Column('min_score', sa.Float(), nullable=True))


def downgrade():
    """Remove the min_score column."""
    op.drop_column('recognizers', 'min_score')
