"""Add interview_records library tables.

Revision ID: 014_interview_records
Revises: 013_profile_contacts
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "014_interview_records"
down_revision: Union[str, None] = "013_profile_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=True),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=True),
        sa.Column("interview_round", sa.String(length=64), nullable=False),
        sa.Column("interviewed_on", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("strong_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("weak_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("gap_type", sa.String(length=32), nullable=True),
        sa.Column("gap_why", sa.Text(), nullable=True),
        sa.Column("recommended_next_action", sa.Text(), nullable=True),
        sa.Column("coaching", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_records_profile_id", "interview_records", ["profile_id"])
    op.create_index("ix_interview_records_mission_id", "interview_records", ["mission_id"])
    op.create_index("ix_interview_records_company", "interview_records", ["company"])
    op.create_index("ix_interview_records_interviewed_on", "interview_records", ["interviewed_on"])

    op.create_table(
        "interview_record_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("my_answer", sa.Text(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["interview_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("record_id", "sort_order", name="uq_interview_record_items_order"),
    )
    op.create_index("ix_interview_record_items_record_id", "interview_record_items", ["record_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_record_items_record_id", table_name="interview_record_items")
    op.drop_table("interview_record_items")
    op.drop_index("ix_interview_records_interviewed_on", table_name="interview_records")
    op.drop_index("ix_interview_records_company", table_name="interview_records")
    op.drop_index("ix_interview_records_mission_id", table_name="interview_records")
    op.drop_index("ix_interview_records_profile_id", table_name="interview_records")
    op.drop_table("interview_records")
