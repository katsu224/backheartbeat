"""Add watch_rooms and watch_clips tables

Revision ID: 007
Revises: 006
Create Date: 2026-05-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watch_rooms",
        sa.Column("room_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("couple_id", UUID(as_uuid=True), sa.ForeignKey("couples.couple_id", ondelete="CASCADE"), nullable=False),
        sa.Column("host_user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.Text, nullable=False),
        sa.Column("video_title", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_watch_rooms_couple_id", "watch_rooms", ["couple_id"])

    op.create_table(
        "watch_clips",
        sa.Column("clip_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("room_id", UUID(as_uuid=True), sa.ForeignKey("watch_rooms.room_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("label", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_watch_clips_room_id", "watch_clips", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_watch_clips_room_id", "watch_clips")
    op.drop_table("watch_clips")
    op.drop_index("ix_watch_rooms_couple_id", "watch_rooms")
    op.drop_table("watch_rooms")
