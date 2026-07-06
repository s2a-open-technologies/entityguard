"""
Seed a recognizer for full German street addresses.
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
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    """Seed a recognizer that matches a full street address as one span.

    Without this, spaCy's generic LOCATION recognizer tends to split an
    address like "Hauptstr. 5, 12345 Musterstadt" into disconnected
    fragments (e.g. "Hauptstr" and "Musterstadt" separately). This
    recognizer matches street name + house number + postal code + city as a
    single LOCATION match, so it is masked as one placeholder instead of
    several fragmented ones.
    """

    op.execute("""
        INSERT INTO recognizers (name, supported_entity, supported_language, is_active, created_at, updated_at)
        VALUES ('adressen_de', 'LOCATION', 'de', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)

    address_id = "(SELECT id FROM recognizers WHERE name = 'adressen_de')"

    # Bound as a parameter (not interpolated into the SQL string) so the
    # colon in "(?:...)" isn't mistaken for a SQLAlchemy bind marker.
    regex = (
        r'(?:[A-ZÄÖÜ][a-zäöüß]+[- ]?){1,3}'
        r'(?:straße|str\.?|weg|allee|platz|ring|damm|gasse)'
        r'\s+\d{1,4}\s?[a-zA-Z]?,?\s*\d{5}\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-]+'
    )
    op.execute(
        sa.text(f"""
            INSERT INTO patterns (name, regex, score, recognizer_id, created_at, updated_at)
            VALUES ('strasse_hausnummer_plz_ort', :regex, 0.85, {address_id}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """).bindparams(regex=regex)
    )

    context_words = ['wohnhaft', 'wohnt', 'adresse', 'gemeldet', 'wohnort']
    for word in context_words:
        op.execute(f"""
            INSERT INTO context_words (word, recognizer_id, created_at)
            VALUES ('{word}', {address_id}, CURRENT_TIMESTAMP)
        """)


def downgrade():
    """Remove the seeded address recognizer (cascades to patterns and context_words)."""
    op.execute("DELETE FROM recognizers WHERE name = 'adressen_de'")
