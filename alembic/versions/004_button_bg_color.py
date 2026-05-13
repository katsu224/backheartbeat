"""Add bg_color to buttons

Revision ID: 004
Revises: 003
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("buttons", sa.Column("bg_color", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("buttons", "bg_color")
