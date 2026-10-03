"""
Add a content-free request trace table (tracing lite).
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
revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    """Create the request_trace table.

    Stores only metadata about sanitize requests (source, key prefix, input
    length, mask counts, entity-type counts, latency, success, optional
    keyed hash) - never the text or the mapping. Rows are pruned according
    to TRACE_RETENTION_DAYS.
    """
    op.create_table(
        'request_trace',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('api_key_prefix', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('input_length', sa.Integer(), nullable=False),
        sa.Column('mask_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('entity_counts', sa.Text(), nullable=True),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('input_hmac', sa.String(length=64), nullable=True),
    )


def downgrade():
    """Drop the request_trace table."""
    op.drop_table('request_trace')
