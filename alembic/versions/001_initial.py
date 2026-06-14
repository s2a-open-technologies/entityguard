"""
Initial migration with all tables..
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

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create recognizers table
    op.create_table(
        'recognizers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('supported_entity', sa.String(100), nullable=False),
        sa.Column('supported_language', sa.String(10), default='de'),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # Create patterns table
    op.create_table(
        'patterns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('regex', sa.Text(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('recognizer_id', sa.Integer(), sa.ForeignKey('recognizers.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )

    # Create context_words table
    op.create_table(
        'context_words',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('word', sa.String(100), nullable=False),
        sa.Column('recognizer_id', sa.Integer(), sa.ForeignKey('recognizers.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.utcnow()),
    )

    # Create admin_users table
    op.create_table(
        'admin_users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(128), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.utcnow()),
        sa.Column('last_password_change', sa.DateTime(), nullable=True),
    )

    # Create entities table
    op.create_table(
        'entities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('placeholder', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.utcnow()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.utcnow(), onupdate=sa.func.utcnow()),
    )


def downgrade() -> None:
    op.drop_table('admin_users')
    op.drop_table('entities')
    op.drop_table('context_words')
    op.drop_table('patterns')
    op.drop_table('recognizers')