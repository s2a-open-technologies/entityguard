"""
Add a salutation-based PERSON pattern (e.g. "Frau Stolz", "Herr Meier").
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
revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

# Salutation/title + capitalised name (up to a compound surname). Catches
# names the German spaCy NER misses in running text ("Frau Stolz aus ..."),
# which it otherwise only detects in isolation. Presidio compiles patterns
# with re.IGNORECASE, so the name part uses an inline (?-i:...) group to
# keep the required capital letter - otherwise "aus"/"ist" would be eaten.
PERSON_TITLE_REGEX = (
    r"\b(?i:herr|frau|patient|patientin|dr|prof|med|dipl|oberarzt|oberärztin|"
    r"chefarzt|chefärztin|pfleger|schwester)\.?\s+"
    r"(?:(?i:herr|frau|dr|prof|med|dipl)\.?\s+)*"
    r"(?-i:[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)"
    r"(?:\s+(?-i:[A-ZÄÖÜ][a-zäöüß]+))?"
)


def upgrade():
    """Seed the salutation-based PERSON pattern (idempotent by name)."""
    op.execute(f"""
        INSERT INTO patterns (name, regex, keywords, score, entity_id, created_at, updated_at)
        SELECT 'anrede_name', '{PERSON_TITLE_REGEX}', NULL, 0.7,
               e.id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM entities e
        WHERE e.name = 'PERSON'
          AND NOT EXISTS (SELECT 1 FROM patterns WHERE name = 'anrede_name')
    """)


def downgrade():
    """Remove the salutation-based PERSON pattern."""
    op.execute("DELETE FROM patterns WHERE name = 'anrede_name'")