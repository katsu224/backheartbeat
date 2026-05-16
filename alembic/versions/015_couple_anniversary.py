"""015 move anniversary_date from users to couples

Revision ID: 015
Revises: 014
Create Date: 2026-05-16
"""
import sqlalchemy as sa
from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("couples", sa.Column("anniversary_date", sa.Date(), nullable=True))
    op.drop_column("users", "anniversary_date")


def downgrade():
    op.add_column("users", sa.Column("anniversary_date", sa.Date(), nullable=True))
    op.drop_column("couples", "anniversary_date")
