"""
Seed default admin user.
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
import bcrypt

# revision identifiers, used by Alembic
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    """Create the default admin user if no admin exists yet."""
    connection = op.get_bind()

    # Only seed if admin_users table is empty
    result = connection.execute(sa.text("SELECT COUNT(*) FROM admin_users"))
    count = result.scalar()

    if count == 0:
        password_hash = bcrypt.hashpw(
            "admin".encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        op.execute(
            sa.text(
                """
                INSERT INTO admin_users (username, password_hash, is_active, created_at, last_password_change)
                VALUES (:username, :password_hash, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ).bindparams(username="admin", password_hash=password_hash)
        )


def downgrade():
    """Remove the default admin user seeded by this migration."""
    op.execute("DELETE FROM admin_users WHERE username = 'admin'")
