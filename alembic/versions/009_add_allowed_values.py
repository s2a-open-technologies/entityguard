"""
Add an allow-list table for values that should never be masked.
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
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    """Create the allowed_values table.

    Exact-match strings that are always excluded from masking, regardless
    of which recognizer flagged them (spaCy, BERT, or a custom pattern) -
    wired via Presidio's AnalyzerEngine.analyze(allow_list=...) in
    src/components/cstm_analyzer.py.
    """
    op.create_table(
        'allowed_values',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('value', sa.String(length=255), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade():
    """Drop the allowed_values table."""
    op.drop_table('allowed_values')
