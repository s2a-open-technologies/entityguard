"""
Add user roles and an append-only audit log.
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
revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    """Add admin_users.role and the audit_log table.

    * `role` defaults to 'admin', so the migration-seeded admin keeps full
      access. Roles: 'admin' (everything) and 'viewer' (read-only).
    * `audit_log` records configuration changes and login events - never the
      changed values themselves.
    """
    op.add_column(
        'admin_users',
        sa.Column('role', sa.String(length=20), nullable=False, server_default='admin'),
    )
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('actor_username', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('target_type', sa.String(length=30), nullable=True),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('target_label', sa.String(length=150), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
    )


def downgrade():
    """Drop the audit log and the role column."""
    op.drop_table('audit_log')
    op.drop_column('admin_users', 'role')
