"""add v0.2 resume-to-proof domain

Revision ID: 009_v0_2_resume_to_proof
Revises: 008_p0_completion_sprint
"""

from alembic import op
import sqlalchemy as sa


revision = "009_v0_2_resume_to_proof"
down_revision = "008_p0_completion_sprint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "target_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="CURRENT", nullable=False),
        sa.Column("requirements", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("capabilities", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "content_hash", name="uq_target_jobs_profile_content_hash"),
    )
    op.create_index("ix_target_jobs_profile_id", "target_jobs", ["profile_id"])

    op.create_table(
        "resume_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("target_job_id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("current_text", sa.Text(), nullable=True),
        sa.Column("suggested_text", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("jd_relevance", sa.Text(), nullable=False),
        sa.Column("matched_capabilities", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence_refs", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("readiness_status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("risk_reason", sa.Text(), nullable=False),
        sa.Column("attack_surface", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["target_job_id"], ["target_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resume_claims_target_job_id", "resume_claims", ["target_job_id"])
    op.create_index("ix_resume_claims_profile_id", "resume_claims", ["profile_id"])

    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("target_job_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("round_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_question", sa.Text(), nullable=True),
        sa.Column("next_skill_id", sa.String(length=64), nullable=True),
        sa.Column("strong_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("weak_points", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("gap_type", sa.String(length=32), nullable=True),
        sa.Column("gap_why", sa.Text(), nullable=True),
        sa.Column("gap_evidence", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("recommended_next_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_job_id"], ["target_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["resume_claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_sessions_profile_id", "interview_sessions", ["profile_id"])
    op.create_index("ix_interview_sessions_target_job_id", "interview_sessions", ["target_job_id"])
    op.create_index("ix_interview_sessions_claim_id", "interview_sessions", ["claim_id"])

    op.create_table(
        "interview_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("followup_dimensions", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evaluation", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "round_number", name="uq_interview_turns_round"),
    )
    op.create_index("ix_interview_turns_session_id", "interview_turns", ["session_id"])

    op.create_table(
        "proof_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("why_now", sa.Text(), nullable=False),
        sa.Column("target_claim", sa.Text(), nullable=False),
        sa.Column("target_gap", sa.String(length=32), nullable=False),
        sa.Column("estimated_hours", sa.Float(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("definition_of_done", sa.Text(), nullable=False),
        sa.Column("expected_evidence", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="PROPOSED", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["resume_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["interview_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proof_actions_profile_id", "proof_actions", ["profile_id"])
    op.create_index("ix_proof_actions_claim_id", "proof_actions", ["claim_id"])
    op.create_index("ix_proof_actions_session_id", "proof_actions", ["session_id"])

    op.create_table(
        "proof_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("artifact_url", sa.Text(), nullable=True),
        sa.Column("artifact_text", sa.Text(), nullable=True),
        sa.Column("manually_confirmed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("verified_fields", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_id"], ["resume_claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_id"], ["proof_actions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proof_artifacts_profile_id", "proof_artifacts", ["profile_id"])
    op.create_index("ix_proof_artifacts_claim_id", "proof_artifacts", ["claim_id"])
    op.create_index("ix_proof_artifacts_action_id", "proof_artifacts", ["action_id"])


def downgrade() -> None:
    op.drop_table("proof_artifacts")
    op.drop_table("proof_actions")
    op.drop_table("interview_turns")
    op.drop_table("interview_sessions")
    op.drop_table("resume_claims")
    op.drop_table("target_jobs")
