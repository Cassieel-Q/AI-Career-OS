"""create target role selections

Revision ID: 006_target_roles
Revises: 005_role_explorations
"""

from alembic import op
import sqlalchemy as sa


revision = "006_target_roles"
down_revision = "005_role_explorations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "target_roles",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_code", sa.String(length=64), nullable=False),
        sa.Column("role_profile_version", sa.String(length=32), nullable=False),
        sa.Column(
            "role_exploration_id",
            sa.Uuid(),
            sa.ForeignKey("role_explorations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "selected_at",
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
    )
    op.create_index("ix_target_roles_profile_id", "target_roles", ["profile_id"], unique=True)
    op.create_index(
        "ix_target_roles_role_exploration_id",
        "target_roles",
        ["role_exploration_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_target_roles_role_exploration_id", table_name="target_roles")
    op.drop_index("ix_target_roles_profile_id", table_name="target_roles")
    op.drop_table("target_roles")
