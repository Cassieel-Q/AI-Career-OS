"""add AI assistant conversations, referrals and reminders

Revision ID: 018_assistant
Revises: 017_job_applications
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "018_assistant"
down_revision = "017_job_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversations",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("surface", sa.String(16), nullable=False, server_default="page"),
        sa.Column("title", sa.String(255), nullable=False, server_default="新对话"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_conversations_surface", "assistant_conversations", ["surface"])

    op.create_table(
        "assistant_messages",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_calls", JSON(), nullable=True),
        sa.Column("sources", JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assistant_messages_conversation_id", "assistant_messages", ["conversation_id"])

    op.create_table(
        "referrals",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("contact", sa.String(255), nullable=True),
        sa.Column("channel", sa.String(128), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="进行中"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_referrals_profile_id", "referrals", ["profile_id"])

    op.create_table(
        "reminders",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_reminders_profile_id", "reminders", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_reminders_profile_id", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_referrals_profile_id", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("ix_assistant_messages_conversation_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_conversations_surface", table_name="assistant_conversations")
    op.drop_table("assistant_conversations")
