"""evidence_os tables (eos_*)

Revision ID: 011_evidence_os
Revises: 010_v02_integrated_job_mission
Create Date: 2026-09-22
"""

from alembic import op
import sqlalchemy as sa


revision = "011_evidence_os"
down_revision = "010_v02_integrated_job_mission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eos_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_sources_profile_id", "eos_sources", ["profile_id"])

    op.create_table(
        "eos_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("org_or_project", sa.Text(), nullable=True),
        sa.Column("identity_lock", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metric", sa.JSON(), nullable=True),
        sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_evidence_profile_id", "eos_evidence", ["profile_id"])

    op.create_table(
        "eos_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("source_fact", sa.Text(), nullable=False),
        sa.Column("candidate_wording", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("responsibility_level", sa.String(length=32), nullable=False, server_default="contributed"),
        sa.Column("boundary", sa.Text(), nullable=False, server_default=""),
        sa.Column("interview_details", sa.Text(), nullable=False, server_default=""),
        sa.Column("risk_notes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("competency_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_claims_profile_id", "eos_claims", ["profile_id"])

    op.create_table(
        "eos_jds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Untitled role"),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_jds_profile_id", "eos_jds", ["profile_id"])

    op.create_table(
        "eos_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("jd_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="core"),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("competency_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["jd_id"], ["eos_jds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_requirements_jd_id", "eos_requirements", ["jd_id"])

    op.create_table(
        "eos_match_rows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("jd_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("match_status", sa.String(length=32), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("excavation_questions", sa.JSON(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["jd_id"], ["eos_jds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_id"], ["eos_requirements.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jd_id", "requirement_id", name="uq_eos_match_jd_req"),
    )
    op.create_index("ix_eos_match_rows_profile_id", "eos_match_rows", ["profile_id"])

    op.create_table(
        "eos_resume_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("jd_id", sa.Uuid(), nullable=True),
        sa.Column("positioning_mode", sa.String(length=16), nullable=False, server_default="conservative"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("full_text_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("bullets", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("excluded", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("audit_safe", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["jd_id"], ["eos_jds.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_resume_versions_profile_id", "eos_resume_versions", ["profile_id"])

    op.create_table(
        "eos_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("full_text_hash", sa.String(length=64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approver", sa.String(length=32), nullable=False, server_default="user"),
        sa.ForeignKeyConstraint(["version_id"], ["eos_resume_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_approvals_version_id", "eos_approvals", ["version_id"])

    op.create_table(
        "eos_eval_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("is_heuristic", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("missing_items", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["eos_resume_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eos_eval_reports_version_id", "eos_eval_reports", ["version_id"])


def downgrade() -> None:
    for t in (
        "eos_eval_reports",
        "eos_approvals",
        "eos_resume_versions",
        "eos_match_rows",
        "eos_requirements",
        "eos_jds",
        "eos_claims",
        "eos_evidence",
        "eos_sources",
    ):
        op.drop_table(t)
