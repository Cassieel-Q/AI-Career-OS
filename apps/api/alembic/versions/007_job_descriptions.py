"""store raw job description samples for the current target role

Revision ID: 007_job_descriptions
Revises: 006_target_roles
"""

from alembic import op
import sqlalchemy as sa


revision = "007_job_descriptions"
down_revision = "006_target_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_descriptions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "target_role_id",
            sa.Uuid(),
            sa.ForeignKey("target_roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "target_role_id", "content_hash", name="uq_job_descriptions_target_role_content_hash"
        ),
    )
    op.create_index("ix_job_descriptions_target_role_id", "job_descriptions", ["target_role_id"])


def downgrade() -> None:
    op.drop_index("ix_job_descriptions_target_role_id", table_name="job_descriptions")
    op.drop_table("job_descriptions")
