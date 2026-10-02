"""
Restructure: entities become the central unit; drop the recognizer layer.
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
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    """Move patterns/context words onto entities and drop recognizers.

    Before: recognizers -> patterns/context_words, where `recognizers`
    mixed real regex rules (is_builtin=0) with inert placeholder rows
    (spaCy/builtin_*) and transformer model toggles. After:

    * `entities` is the single configuration unit; `patterns` and
      `context_words` reference it directly via `entity_id`.
    * transformer toggles live in the new `detector_models` table.
    * the recognizer layer (and all its inert rows) is gone.

    Only patterns/context words attached to a real entity survive; rows
    pointing at builtin placeholders (e.g. builtin_credit_card with no
    matching entity) are discarded.
    """
    # 1. Transformer toggles -> detector_models
    op.execute("""
        CREATE TABLE detector_models (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    op.execute("""
        INSERT INTO detector_models (name, is_active, created_at, updated_at)
        SELECT name, is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM recognizers
        WHERE name LIKE 'transformer%'
    """)

    # 2. Rebuild patterns: add entity_id/keywords, drop recognizer_id,
    #    keep only rows that map to a real entity.
    op.execute("""
        CREATE TABLE patterns_new (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            regex TEXT NOT NULL,
            keywords TEXT,
            score FLOAT NOT NULL,
            entity_id INTEGER NOT NULL REFERENCES entities(id),
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    op.execute("""
        INSERT INTO patterns_new (id, name, regex, keywords, score, entity_id, created_at, updated_at)
        SELECT p.id, p.name, p.regex, NULL, p.score, e.id, p.created_at, p.updated_at
        FROM patterns p
        JOIN recognizers r ON p.recognizer_id = r.id
        JOIN entities e ON e.name = r.supported_entity
    """)
    op.execute("DROP TABLE patterns")
    op.execute("ALTER TABLE patterns_new RENAME TO patterns")

    # 3. Rebuild context_words the same way.
    op.execute("""
        CREATE TABLE context_words_new (
            id INTEGER PRIMARY KEY,
            word VARCHAR(100) NOT NULL,
            entity_id INTEGER NOT NULL REFERENCES entities(id),
            created_at DATETIME
        )
    """)
    op.execute("""
        INSERT INTO context_words_new (id, word, entity_id, created_at)
        SELECT cw.id, cw.word, e.id, cw.created_at
        FROM context_words cw
        JOIN recognizers r ON cw.recognizer_id = r.id
        JOIN entities e ON e.name = r.supported_entity
    """)
    op.execute("DROP TABLE context_words")
    op.execute("ALTER TABLE context_words_new RENAME TO context_words")

    # 4. Drop the recognizer layer entirely.
    op.execute("DROP TABLE recognizers")


def downgrade():
    """Best-effort restore of the recognizer layer.

    Recreates `recognizers` with one row per entity (the old setup could
    hold several; they were merged by upgrade) and moves patterns/context
    words back. Transformer toggles are restored from `detector_models`.
    """
    op.execute("""
        CREATE TABLE recognizers (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            supported_entity VARCHAR(100) NOT NULL,
            supported_language VARCHAR(10),
            is_active BOOLEAN,
            is_builtin BOOLEAN,
            min_score FLOAT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)

    # One recognizer per entity that carries patterns or context words...
    op.execute("""
        INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
        SELECT DISTINCT e.name || '_erkennung', e.name, 'de', e.is_active, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM entities e
        WHERE e.id IN (SELECT entity_id FROM patterns)
           OR e.id IN (SELECT entity_id FROM context_words)
    """)
    # ...plus the transformer rows from detector_models.
    op.execute("""
        INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
        SELECT name, name, 'de', is_active, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM detector_models
    """)

    # Move patterns/context back, keyed by the synthetic recognizer names.
    op.execute("""
        CREATE TABLE patterns_old (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            regex TEXT NOT NULL,
            score FLOAT NOT NULL,
            recognizer_id INTEGER NOT NULL REFERENCES recognizers(id),
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    op.execute("""
        INSERT INTO patterns_old (id, name, regex, score, recognizer_id, created_at, updated_at)
        SELECT p.id, p.name, p.regex, p.score, r.id, p.created_at, p.updated_at
        FROM patterns p
        JOIN entities e ON p.entity_id = e.id
        JOIN recognizers r ON r.name = e.name || '_erkennung'
    """)
    op.execute("DROP TABLE patterns")
    op.execute("ALTER TABLE patterns_old RENAME TO patterns")

    op.execute("""
        CREATE TABLE context_words_old (
            id INTEGER PRIMARY KEY,
            word VARCHAR(100) NOT NULL,
            recognizer_id INTEGER NOT NULL REFERENCES recognizers(id),
            created_at DATETIME
        )
    """)
    op.execute("""
        INSERT INTO context_words_old (id, word, recognizer_id, created_at)
        SELECT cw.id, cw.word, r.id, cw.created_at
        FROM context_words cw
        JOIN entities e ON cw.entity_id = e.id
        JOIN recognizers r ON r.name = e.name || '_erkennung'
    """)
    op.execute("DROP TABLE context_words")
    op.execute("ALTER TABLE context_words_old RENAME TO context_words")

    op.execute("DROP TABLE detector_models")