"""Add builtin Presidio recognizers to database

Revision ID: 003
Revises: 002
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    """Add is_builtin column and seed builtin recognizers."""

    # Add is_builtin column to recognizers table with default value
    op.add_column('recognizers', sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default='0'))

    # Update existing recognizers to is_builtin=False
    op.execute("UPDATE recognizers SET is_builtin = 0")

    # Insert builtin Presidio recognizers
    # These represent the built-in recognizers that Presidio loads automatically
    builtin_recognizers = [
        # SpacyRecognizer - detects via NLP model
        ('spacy_person', 'PERSON', 'de', 1, 1),
        ('spacy_location', 'LOCATION', 'de', 1, 1),
        ('spacy_organization', 'ORGANIZATION', 'de', 1, 1),
        ('spacy_date_time', 'DATE_TIME', 'de', 1, 1),

        # Pattern-based builtin recognizers
        ('builtin_phone', 'PHONE_NUMBER', 'de', 1, 1),
        ('builtin_email', 'EMAIL_ADDRESS', 'de', 1, 1),
        ('builtin_iban', 'IBAN_CODE', 'de', 1, 1),
        ('builtin_ip', 'IP_ADDRESS', 'de', 1, 1),
        ('builtin_credit_card', 'CREDIT_CARD', 'de', 1, 1),
    ]

    for name, entity, lang, is_active, is_builtin in builtin_recognizers:
        op.execute(f"""
            INSERT INTO recognizers (name, supported_entity, supported_language, is_active, is_builtin, created_at, updated_at)
            VALUES ('{name}', '{entity}', '{lang}', {is_active}, {is_builtin}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET is_builtin = {is_builtin}, is_active = {is_active}
        """)


def downgrade():
    """Remove builtin recognizers and is_builtin column."""
    # Delete builtin recognizers
    op.execute("DELETE FROM recognizers WHERE is_builtin = 1")

    # Remove is_builtin column
    op.drop_column('recognizers', 'is_builtin')
