"""Add the mission-scoped Resume Studio document."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision = "014_resume_studio"
down_revision: Union[str, None] = "013_profile_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_studio_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mission_id", sa.Uuid(), sa.ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_target_resume_id", sa.Uuid(), sa.ForeignKey("target_resumes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("language", sa.String(2), nullable=False, server_default="zh"),
        sa.Column("template_id", sa.String(64), nullable=False, server_default="zh-classic"),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("confirmed_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("mission_id", name="uq_resume_studio_mission"),
    )
    op.create_index("ix_resume_studio_documents_mission_id", "resume_studio_documents", ["mission_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_studio_documents_mission_id", table_name="resume_studio_documents")
    op.drop_table("resume_studio_documents")
