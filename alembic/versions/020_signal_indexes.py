"""020 add indexes on signals(sender_id, created_at) and (receiver_id, created_at)

Revision ID: 020
Revises: 019
Create Date: 2026-05-17
"""
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_signals_sender_created", "signals", ["sender_id", "created_at"])
    op.create_index("ix_signals_receiver_created", "signals", ["receiver_id", "created_at"])


def downgrade():
    op.drop_index("ix_signals_sender_created", table_name="signals")
    op.drop_index("ix_signals_receiver_created", table_name="signals")
