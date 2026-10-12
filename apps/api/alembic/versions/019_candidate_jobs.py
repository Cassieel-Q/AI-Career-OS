"""add candidate job staging area

Revision ID: 019_candidate_jobs
Revises: 018_assistant
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "019_candidate_jobs"
down_revision = "018_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_jobs",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_kind", sa.String(32), nullable=False, server_default="PASTE"),
        sa.Column("recognition_source", sa.String(32), nullable=False, server_default="HEURISTIC_SPLIT"),
        sa.Column("source_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_excerpt_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("raw_payload", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("imported_mission_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["imported_mission_id"], ["job_missions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "profile_id", "source_hash", "source_excerpt_hash", name="uq_candidate_jobs_profile_source_excerpt"
        ),
    )
    op.create_index("ix_candidate_jobs_profile_id", "candidate_jobs", ["profile_id"])
    op.create_index("ix_candidate_jobs_imported_mission_id", "candidate_jobs", ["imported_mission_id"])
    op.create_index("ix_candidate_jobs_profile_status", "candidate_jobs", ["profile_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_candidate_jobs_profile_status", table_name="candidate_jobs")
    op.drop_index("ix_candidate_jobs_imported_mission_id", table_name="candidate_jobs")
    op.drop_index("ix_candidate_jobs_profile_id", table_name="candidate_jobs")
    op.drop_table("candidate_jobs")
