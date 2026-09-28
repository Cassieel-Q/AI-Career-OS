"""add integrated v0.2 Job Mission vertical slice

Revision ID: 010_v02_integrated_job_mission
Revises: 009_v0_2_resume_to_proof
"""

from alembic import op
import sqlalchemy as sa


revision = "010_v02_integrated_job_mission"
down_revision = "009_v0_2_resume_to_proof"
branch_labels = None
depends_on = None


def _uuid_column(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "job_missions",
        _uuid_column("id"),
        _uuid_column("profile_id"),
        _uuid_column("target_job_id"),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), server_default="UNKNOWN", nullable=False),
        sa.Column("role", sa.String(length=255), server_default="UNKNOWN", nullable=False),
        sa.Column("role_family", sa.String(length=64), server_default="UNKNOWN", nullable=False),
        sa.Column("seniority", sa.String(length=64), server_default="UNKNOWN", nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("parsed_jd", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("what_matters", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("resume_strategy", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("interview_intel", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_job_id"], ["target_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "target_job_id", name="uq_job_missions_profile_target_job"),
    )
    op.create_index("ix_job_missions_profile_id", "job_missions", ["profile_id"])
    op.create_index("ix_job_missions_target_job_id", "job_missions", ["target_job_id"])

    op.create_table(
        "mission_experience_selections",
        _uuid_column("id"),
        _uuid_column("mission_id"),
        _uuid_column("profile_id"),
        _uuid_column("experience_id"),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("related_capabilities", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("supporting_evidence_refs", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "experience_id", name="uq_mission_experience_selection"),
    )
    op.create_index("ix_mission_experience_selections_mission_id", "mission_experience_selections", ["mission_id"])
    op.create_index("ix_mission_experience_selections_profile_id", "mission_experience_selections", ["profile_id"])
    op.create_index("ix_mission_experience_selections_experience_id", "mission_experience_selections", ["experience_id"])

    op.create_table(
        "target_resumes",
        _uuid_column("id"),
        _uuid_column("mission_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("positioning_statement", sa.Text(), nullable=True),
        sa.Column("recommended_experience_order", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("strategy", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "version", name="uq_target_resumes_mission_version"),
    )
    op.create_index("ix_target_resumes_mission_id", "target_resumes", ["mission_id"])

    op.create_table(
        "target_resume_bullets",
        _uuid_column("id"),
        _uuid_column("target_resume_id"),
        _uuid_column("source_experience_id", nullable=True),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("suggested_text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("jd_refs", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("evidence_refs", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("resume_skill_refs", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("risk_flags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="SUGGESTED", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["target_resume_id"], ["target_resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_target_resume_bullets_target_resume_id", "target_resume_bullets", ["target_resume_id"])
    op.create_index("ix_target_resume_bullets_source_experience_id", "target_resume_bullets", ["source_experience_id"])

    op.create_table(
        "red_team_reports",
        _uuid_column("id"),
        _uuid_column("mission_id"),
        _uuid_column("target_resume_id"),
        sa.Column("findings", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_resume_id"], ["target_resumes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_red_team_reports_mission_id", "red_team_reports", ["mission_id"])
    op.create_index("ix_red_team_reports_target_resume_id", "red_team_reports", ["target_resume_id"])

    op.create_table(
        "interview_packs",
        _uuid_column("id"),
        _uuid_column("mission_id"),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("topics", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mission_id", "version", name="uq_interview_packs_mission_version"),
    )
    op.create_index("ix_interview_packs_mission_id", "interview_packs", ["mission_id"])

    op.create_table(
        "interview_outcomes",
        _uuid_column("id"),
        _uuid_column("mission_id"),
        sa.Column("application_status", sa.String(length=32), nullable=False),
        sa.Column("interview_round", sa.String(length=64), nullable=True),
        sa.Column("questions_asked", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("where_struggled", sa.Text(), nullable=True),
        sa.Column("interviewer_feedback", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("confirmed_for_intel", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_outcomes_mission_id", "interview_outcomes", ["mission_id"])

    op.add_column("interview_sessions", sa.Column("mission_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_interview_sessions_mission_id_job_missions",
        "interview_sessions",
        "job_missions",
        ["mission_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_interview_sessions_mission_id", "interview_sessions", ["mission_id"])

    op.add_column("proof_actions", sa.Column("mission_id", sa.Uuid(), nullable=True))
    op.add_column("proof_actions", sa.Column("target_capability", sa.String(length=255), nullable=True))
    op.add_column("proof_actions", sa.Column("existing_project_reference", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_proof_actions_mission_id_job_missions",
        "proof_actions",
        "job_missions",
        ["mission_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_proof_actions_mission_id", "proof_actions", ["mission_id"])


def downgrade() -> None:
    raise RuntimeError("Downgrade is intentionally unsupported for the integrated dogfood migration")
