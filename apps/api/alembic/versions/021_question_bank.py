"""add standalone question bank and grounded reference answers

Revision ID: 021_question_bank
Revises: 020_profile_boundary
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "021_question_bank"
down_revision = "020_profile_boundary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "question_banks",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("mission_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default="默认题库"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_question_banks_profile_id", "question_banks", ["profile_id"])
    op.create_index("ix_question_banks_mission_id", "question_banks", ["mission_id"])

    op.create_table(
        "question_items",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("bank_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("interviewer_style", sa.String(64), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(24), nullable=False, server_default="MODEL"),
        sa.Column("evidence_refs", JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["bank_id"], ["question_banks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_question_items_bank_id", "question_items", ["bank_id"])

    op.create_table(
        "reference_answers",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("question_item_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("grounding", sa.String(32), nullable=False, server_default="NEEDS_CONFIRMATION"),
        sa.Column("evidence_refs", JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["question_item_id"], ["question_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reference_answers_question_item_id", "reference_answers", ["question_item_id"])


def downgrade() -> None:
    op.drop_index("ix_reference_answers_question_item_id", table_name="reference_answers")
    op.drop_table("reference_answers")
    op.drop_index("ix_question_items_bank_id", table_name="question_items")
    op.drop_table("question_items")
    op.drop_index("ix_question_banks_mission_id", table_name="question_banks")
    op.drop_index("ix_question_banks_profile_id", table_name="question_banks")
    op.drop_table("question_banks")
