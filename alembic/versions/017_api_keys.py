"""
Add an API-key table for the JSON API.
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
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    """Create the api_keys table.

    API keys are created and managed exclusively in the admin UI. Only the
    bcrypt hash is stored (a lost key cannot be recovered). While no active
    key exists, /api/v1/sanitize and /api/v1/reload return HTTP 401
    (fail-closed).
    """
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_prefix', sa.String(length=120), nullable=False),
        sa.Column('key_hash', sa.String(length=128), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    """Drop the api_keys table."""
    op.drop_table('api_keys')
