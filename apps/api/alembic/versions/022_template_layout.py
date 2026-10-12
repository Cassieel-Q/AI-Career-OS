"""add unified layout config and template drafts

Revision ID: 022_template_layout
Revises: 021_question_bank
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import JSON, Uuid


revision = "022_template_layout"
down_revision = "021_question_bank"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resume_studio_documents",
        sa.Column("layout_config", JSON(), nullable=False, server_default=sa.text("'{}'")),
    )

    op.create_table(
        "resume_template_drafts",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("layout_config", JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("sanitized_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("warnings", JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_resume_template_drafts_profile_id", "resume_template_drafts", ["profile_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_template_drafts_profile_id", table_name="resume_template_drafts")
    op.drop_table("resume_template_drafts")
    op.drop_column("resume_studio_documents", "layout_config")
