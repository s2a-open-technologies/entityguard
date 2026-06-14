"""
Seed remaining default entities.
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
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Upsert remaining default entities used by EntityGuard."""

    # Ensure FALLNUMMER entity exists (used for explicit medical case numbers)
    entities = [
        ('FALLNUMMER', '[FALLNUMMER]', 'Medizinische Fallnummern'),
    ]

    for name, placeholder, description in entities:
        op.execute(f"""
            INSERT INTO entities (name, placeholder, description, is_active, created_at, updated_at)
            VALUES ('{name}', '{placeholder}', '{description}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET placeholder = '{placeholder}', is_active = 1, updated_at = CURRENT_TIMESTAMP
        """)


def downgrade():
    """Remove the entities seeded by this migration."""
    op.execute("DELETE FROM entities WHERE name = 'FALLNUMMER'")
