"""add normalized profile fields

Revision ID: 002_profile_normalization
Revises: 001_create_profile_tables
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "002_profile_normalization"
down_revision = "001_create_profile_tables"
branch_labels = None
depends_on = None


EXPERIENCE_TYPES = "'WORK', 'INTERNSHIP', 'CAMPUS', 'PROJECT', 'OTHER'"


def upgrade() -> None:
    op.add_column(
        "education",
        sa.Column("relevant_courses", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "experiences",
        sa.Column("experience_type", sa.String(length=16), nullable=False, server_default="OTHER"),
    )
    op.create_check_constraint(
        "ck_experiences_experience_type",
        "experiences",
        f"experience_type IN ({EXPERIENCE_TYPES})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_experiences_experience_type", "experiences", type_="check")
    op.drop_column("experiences", "experience_type")
    op.drop_column("education", "relevant_courses")
