"""create role exploration snapshots

Revision ID: 005_role_explorations
Revises: 004_career_preferences
"""

from alembic import op
import sqlalchemy as sa


revision = "005_role_explorations"
down_revision = "004_career_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "role_explorations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_profile_version", sa.String(length=32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint("profile_id", name="uq_role_explorations_profile_id"),
    )
    op.create_index("ix_role_explorations_profile_id", "role_explorations", ["profile_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_role_explorations_profile_id", table_name="role_explorations")
    op.drop_table("role_explorations")

