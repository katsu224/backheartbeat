"""Add username and password_hash to users

Revision ID: 002
Revises: 001
Create Date: 2024-01-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first so existing rows don't break
    op.add_column("users", sa.Column("username", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))

    # Assign a unique username to any pre-existing test rows
    op.execute(
        "UPDATE users SET username = 'legacy_' || LEFT(CAST(user_id AS VARCHAR), 8) "
        "WHERE username IS NULL"
    )
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")

    # Make them NOT NULL now that all rows have values
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "password_hash", nullable=False)

    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_index("ix_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
