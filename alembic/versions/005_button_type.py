"""Add button_type column

Revision ID: 005
Revises: 004
Create Date: 2026-05-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "buttons",
        sa.Column("button_type", sa.String(10), nullable=False, server_default="text"),
    )


def downgrade() -> None:
    op.drop_column("buttons", "button_type")
