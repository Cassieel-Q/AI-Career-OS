"""create career preferences

Revision ID: 004_career_preferences
Revises: 003_credential_details
Create Date: 2026-09-12
"""

from alembic import op
import sqlalchemy as sa


revision = "004_career_preferences"
down_revision = "003_credential_details"
branch_labels = None
depends_on = None

PRIORITIES = "'COMPENSATION', 'LESS_CODING', 'FAST_EMPLOYMENT', 'CURRENT_FIT', 'LONG_TERM_GROWTH'"


def upgrade() -> None:
    op.create_table(
        "career_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority_1", sa.String(length=32), nullable=False),
        sa.Column("priority_2", sa.String(length=32), nullable=False),
        sa.Column("weekly_hours", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("profile_id", name="uq_career_preferences_profile_id"),
        sa.CheckConstraint(f"priority_1 IN ({PRIORITIES})", name="ck_career_preferences_priority_1"),
        sa.CheckConstraint(f"priority_2 IN ({PRIORITIES})", name="ck_career_preferences_priority_2"),
        sa.CheckConstraint("priority_1 <> priority_2", name="ck_career_preferences_priorities_distinct"),
        sa.CheckConstraint("weekly_hours BETWEEN 1 AND 60", name="ck_career_preferences_weekly_hours"),
    )


def downgrade() -> None:
    op.drop_table("career_preferences")
