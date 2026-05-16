"""014 add avatar and anniversary to users

Revision ID: 014
Revises: 013
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar_path", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("anniversary_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("users", "anniversary_date")
    op.drop_column("users", "avatar_path")
