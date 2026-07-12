"""add conversations table

Revision ID: a1b2c3d4e5f6
Revises: 6314ab255d67
Create Date: 2026-07-10 12:00:00.000000+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "6314ab255d67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("patient_id", sa.UUID(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reply", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversations_phone"), "conversations", ["phone"], unique=False
    )
    op.create_index(
        op.f("ix_conversations_patient_id"),
        "conversations",
        ["patient_id"],
        unique=False,
    )
    op.create_index(
        "ix_conversations_phone_channel",
        "conversations",
        ["phone", "channel"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_phone_channel", table_name="conversations")
    op.drop_index(
        op.f("ix_conversations_patient_id"), table_name="conversations"
    )
    op.drop_index(op.f("ix_conversations_phone"), table_name="conversations")
    op.drop_table("conversations")
