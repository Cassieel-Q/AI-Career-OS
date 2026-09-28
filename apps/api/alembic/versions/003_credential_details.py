"""add credential score and status fields

Revision ID: 003_credential_details
Revises: 002_profile_normalization
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "003_credential_details"
down_revision = "002_profile_normalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("education", "profile_skills", "experiences", "certifications"):
        op.add_column(table, sa.Column("raw_value", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("canonical_value", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("evidence_start", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("evidence_end", sa.Integer(), nullable=True))
    op.add_column("certifications", sa.Column("score", sa.String(length=64), nullable=True))
    op.add_column("certifications", sa.Column("status", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("certifications", "status")
    op.drop_column("certifications", "score")
    for table in ("certifications", "experiences", "profile_skills", "education"):
        op.drop_column(table, "evidence_end")
        op.drop_column(table, "evidence_start")
        op.drop_column(table, "canonical_value")
        op.drop_column(table, "raw_value")
