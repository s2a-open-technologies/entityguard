"""
Add app_settings for admin-editable runtime settings (image/OCR).
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
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


DEFAULTS = {
    'ocr_enabled': 'true',
    'ocr_engine': 'auto',
    'ocr_device': 'auto',
    'ocr_lang': 'deu+eng',
    'ocr_redaction': 'line',
    'ocr_min_confidence': '0.5',
    'ocr_verify': 'false',
    'image_max_bytes': '10485760',
    'image_max_pixels': '40000000',
    'ocr_timeout_seconds': '30',
}


def upgrade():
    """Create app_settings and seed the image/OCR defaults.

    Environment variables override these rows for headless deployments; the
    defaults here only define the initial admin-UI state.
    """
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=100), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    settings = sa.table(
        'app_settings',
        sa.column('key', sa.String()),
        sa.column('value', sa.Text()),
    )
    op.bulk_insert(settings, [{'key': k, 'value': v} for k, v in DEFAULTS.items()])


def downgrade():
    """Drop app_settings."""
    op.drop_table('app_settings')
