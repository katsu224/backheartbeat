"""013 add paired_at to couples

Revision ID: 013
Revises: 012
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "couples",
        sa.Column("paired_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing complete couples using created_at as best approximation
    op.execute(
        "UPDATE couples SET paired_at = created_at WHERE is_complete = TRUE AND paired_at IS NULL"
    )


def downgrade():
    op.drop_column("couples", "paired_at")
