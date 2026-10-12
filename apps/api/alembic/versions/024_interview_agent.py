"""extend question items and interview session config

Revision ID: 024_interview_agent
Revises: 023_write_proposals
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "024_interview_agent"
down_revision = "023_write_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 第六阶段：题目必须能回答「为什么问 / 关联哪条 JD / 用哪段经历 / 哪些事实可说 / 哪些不能编 / 可能怎么追问」。
    op.add_column("question_items", sa.Column("jd_requirement_refs", JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("question_items", sa.Column("experience_refs", JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("question_items", sa.Column("why_asked", sa.Text(), nullable=True))
    op.add_column("question_items", sa.Column("expected_evidence", JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("question_items", sa.Column("followup_paths", JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("question_items", sa.Column("sample_answer", sa.Text(), nullable=True))
    op.add_column("question_items", sa.Column("risk_flags", JSON(), nullable=False, server_default=sa.text("'[]'")))

    # 第七阶段：模拟面试启动参数。
    op.add_column("interview_sessions", sa.Column("config", JSON(), nullable=False, server_default=sa.text("'{}'")))

    # 第七阶段：任务级模拟面试（围绕岗位版简历逐轮追问与评分）。
    op.create_table(
        "mock_interview_sessions",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("mission_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("target_resume_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("interview_type", sa.String(32), nullable=False, server_default="TECHNICAL"),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("interviewer_style", sa.String(64), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("current_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("config", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("report", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_resume_id"], ["target_resumes.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_mock_interview_sessions_profile_id", "mock_interview_sessions", ["profile_id"])
    op.create_index("ix_mock_interview_sessions_mission_id", "mock_interview_sessions", ["mission_id"])
    op.create_index("ix_mock_interview_sessions_target_resume_id", "mock_interview_sessions", ["target_resume_id"])

    op.create_table(
        "mock_interview_turns",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("session_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_source", sa.String(32), nullable=False, server_default="JD_DERIVED"),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("evaluation", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["mock_interview_sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_id", "round_number", name="uq_mock_interview_turns_round"),
    )
    op.create_index("ix_mock_interview_turns_session_id", "mock_interview_turns", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_mock_interview_turns_session_id", table_name="mock_interview_turns")
    op.drop_table("mock_interview_turns")
    op.drop_index("ix_mock_interview_sessions_target_resume_id", table_name="mock_interview_sessions")
    op.drop_index("ix_mock_interview_sessions_mission_id", table_name="mock_interview_sessions")
    op.drop_index("ix_mock_interview_sessions_profile_id", table_name="mock_interview_sessions")
    op.drop_table("mock_interview_sessions")
    op.drop_column("interview_sessions", "config")
    op.drop_column("question_items", "risk_flags")
    op.drop_column("question_items", "sample_answer")
    op.drop_column("question_items", "followup_paths")
    op.drop_column("question_items", "expected_evidence")
    op.drop_column("question_items", "why_asked")
    op.drop_column("question_items", "experience_refs")
    op.drop_column("question_items", "jd_requirement_refs")
