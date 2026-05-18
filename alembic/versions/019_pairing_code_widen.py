"""019 widen pairing_code column to 16 chars

Revision ID: 019
Revises: 018
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "couples",
        "pairing_code",
        existing_type=sa.String(length=6),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "couples",
        "pairing_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=6),
        existing_nullable=False,
    )
