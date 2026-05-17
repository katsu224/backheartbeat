"""016 add media_url to signals

Revision ID: 016
Revises: 015
Create Date: 2026-05-16
"""
import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("signals", sa.Column("media_url", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("signals", "media_url")
