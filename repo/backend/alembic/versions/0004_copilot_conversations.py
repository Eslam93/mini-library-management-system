"""copilot conversations

Copilot conversations, one per user and face, and their messages, which the model reads back as
the context of follow-up questions.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("face", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "face IN ('member', 'staff')", name=op.f("ck_copilot_conversations_face_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_copilot_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copilot_conversations")),
    )
    op.create_index(op.f("ix_copilot_conversations_user_id"), "copilot_conversations", ["user_id"])

    op.create_table(
        "copilot_messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool')", name=op.f("ck_copilot_messages_role_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["copilot_conversations.id"],
            name=op.f("fk_copilot_messages_conversation_id_copilot_conversations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_copilot_messages")),
    )
    op.create_index(
        "ix_copilot_messages_conversation_id_id", "copilot_messages", ["conversation_id", "id"]
    )


def downgrade() -> None:
    # Dropping a table drops its indexes.
    op.drop_table("copilot_messages")
    op.drop_table("copilot_conversations")
