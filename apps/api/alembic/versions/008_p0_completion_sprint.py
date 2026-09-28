"""add p0 completion sprint derived state tables

Revision ID: 008_p0_completion_sprint
Revises: 007_job_descriptions
"""

from alembic import op
import sqlalchemy as sa


revision = "008_p0_completion_sprint"
down_revision = "007_job_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_role_id", sa.Uuid(), nullable=False),
        sa.Column("sample_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["target_role_id"], ["target_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_role_id"),
    )
    op.create_index("ix_market_profiles_target_role_id", "market_profiles", ["target_role_id"])
    op.create_table(
        "market_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("market_profile_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("frequency_ratio", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["market_profile_id"], ["market_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_requirements_market_profile_id", "market_requirements", ["market_profile_id"])
    op.create_table(
        "market_requirement_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("job_description_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["requirement_id"], ["market_requirements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_description_id"], ["job_descriptions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_requirement_evidence_requirement_id", "market_requirement_evidence", ["requirement_id"])
    op.create_index("ix_market_requirement_evidence_job_description_id", "market_requirement_evidence", ["job_description_id"])
    op.create_table(
        "gap_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("market_profile_id", sa.Uuid(), nullable=False),
        sa.Column("profile_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["market_profile_id"], ["market_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_profile_id"),
    )
    op.create_index("ix_gap_analyses_profile_id", "gap_analyses", ["profile_id"])
    op.create_index("ix_gap_analyses_market_profile_id", "gap_analyses", ["market_profile_id"])
    op.create_table(
        "gaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gap_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("market_requirement_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("proximity", sa.String(length=16), nullable=False),
        sa.Column("feasibility", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["gap_analysis_id"], ["gap_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["market_requirement_id"], ["market_requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gap_analysis_id", "market_requirement_id", name="uq_gaps_analysis_requirement"),
    )
    op.create_index("ix_gaps_gap_analysis_id", "gaps", ["gap_analysis_id"])
    op.create_index("ix_gaps_market_requirement_id", "gaps", ["market_requirement_id"])
    op.create_table(
        "gap_priorities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gap_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("gap_id", sa.Uuid(), nullable=False),
        sa.Column("system_rank", sa.Integer(), nullable=False),
        sa.Column("user_rank", sa.Integer(), nullable=True),
        sa.Column("lane", sa.String(length=16), nullable=False),
        sa.Column("system_reason", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gap_analysis_id"], ["gap_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gap_id"),
    )
    op.create_index("ix_gap_priorities_gap_analysis_id", "gap_priorities", ["gap_analysis_id"])
    op.create_index("ix_gap_priorities_gap_id", "gap_priorities", ["gap_id"])
    op.create_table(
        "roadmaps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("gap_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=False),
        sa.Column("priority_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gap_analysis_id"], ["gap_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["roadmaps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roadmaps_profile_id", "roadmaps", ["profile_id"])
    op.create_index("ix_roadmaps_gap_analysis_id", "roadmaps", ["gap_analysis_id"])
    op.create_table(
        "roadmap_weeks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("roadmap_id", sa.Uuid(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("focus_gap_ids", sa.JSON(), nullable=False),
        sa.Column("measurable_outcome", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["roadmap_id"], ["roadmaps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("roadmap_id", "week_number", name="uq_roadmap_weeks_number"),
    )
    op.create_index("ix_roadmap_weeks_roadmap_id", "roadmap_weeks", ["roadmap_id"])
    op.create_table(
        "roadmap_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("roadmap_week_id", sa.Uuid(), nullable=False),
        sa.Column("gap_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("completion_criteria", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gap_id"], ["gaps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["roadmap_week_id"], ["roadmap_weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_roadmap_tasks_roadmap_week_id", "roadmap_tasks", ["roadmap_week_id"])
    op.create_index("ix_roadmap_tasks_gap_id", "roadmap_tasks", ["gap_id"])


def downgrade() -> None:
    op.drop_table("roadmap_tasks")
    op.drop_table("roadmap_weeks")
    op.drop_table("roadmaps")
    op.drop_table("gap_priorities")
    op.drop_table("gaps")
    op.drop_table("gap_analyses")
    op.drop_table("market_requirement_evidence")
    op.drop_table("market_requirements")
    op.drop_table("market_profiles")
