"""add assistant write proposals and receipts

Revision ID: 023_write_proposals
Revises: 022_template_layout
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "023_write_proposals"
down_revision = "022_template_layout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "write_proposals",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("message_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("args", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="PROPOSED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_write_proposals_conversation_id", "write_proposals", ["conversation_id"])
    op.create_index("ix_write_proposals_message_id", "write_proposals", ["message_id"])
    op.create_index("ix_write_proposals_profile_id", "write_proposals", ["profile_id"])

    op.create_table(
        "write_receipts",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("target_table", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("diff", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["proposal_id"], ["write_proposals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("proposal_id", name="uq_write_receipts_proposal_id"),
    )
    op.create_index("ix_write_receipts_proposal_id", "write_receipts", ["proposal_id"])


def downgrade() -> None:
    op.drop_index("ix_write_receipts_proposal_id", table_name="write_receipts")
    op.drop_table("write_receipts")
    op.drop_index("ix_write_proposals_profile_id", table_name="write_proposals")
    op.drop_index("ix_write_proposals_message_id", table_name="write_proposals")
    op.drop_index("ix_write_proposals_conversation_id", table_name="write_proposals")
    op.drop_table("write_proposals")
