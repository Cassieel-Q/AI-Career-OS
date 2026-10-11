"""add honors to education

Revision ID: 016_education_honors
Revises: 015_interview_records
Create Date: 2026-10-11
"""

from alembic import op
import sqlalchemy as sa


revision = "016_education_honors"
down_revision = "015_interview_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("education") as batch:
        batch.add_column(sa.Column("honors", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("education") as batch:
        batch.drop_column("honors")
