"""add job applications tracker

Revision ID: 017_job_applications
Revises: 016_education_honors
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "017_job_applications"
down_revision = "016_education_honors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_applications",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("mission_id", Uuid(as_uuid=True), nullable=True),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("role", sa.String(255), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("channel", sa.String(64), nullable=False, server_default="官网"),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("applied_at", sa.Date(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_job_applications_profile_id", "job_applications", ["profile_id"])
    op.create_index("ix_job_applications_mission_id", "job_applications", ["mission_id"])


def downgrade() -> None:
    op.drop_index("ix_job_applications_mission_id", table_name="job_applications")
    op.drop_index("ix_job_applications_profile_id", table_name="job_applications")
    op.drop_table("job_applications")
