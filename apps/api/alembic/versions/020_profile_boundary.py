"""split ResumeProfile / ApplicationProfile boundary and keep CET scores

Revision ID: 020_profile_boundary
Revises: 019_candidate_jobs
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import Uuid


revision = "020_profile_boundary"
down_revision = "019_candidate_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 教育上保留 CET-4/6 分数（不能只保存「已通过」）。
    op.add_column("education", sa.Column("cet4_score", sa.String(32), nullable=True))
    op.add_column("education", sa.Column("cet6_score", sa.String(32), nullable=True))

    op.create_table(
        "application_profiles",
        sa.Column("id", Uuid(as_uuid=True), primary_key=True),
        sa.Column("profile_id", Uuid(as_uuid=True), nullable=False),
        sa.Column("id_number", sa.String(64), nullable=True),
        sa.Column("family_info", sa.Text(), nullable=True),
        sa.Column("health_status", sa.Text(), nullable=True),
        sa.Column("archive_location", sa.String(255), nullable=True),
        sa.Column("emergency_contact", sa.String(255), nullable=True),
        sa.Column("emergency_phone", sa.String(64), nullable=True),
        sa.Column("availability", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", name="uq_application_profiles_profile_id"),
    )
    op.create_index("ix_application_profiles_profile_id", "application_profiles", ["profile_id"])

    # 数据迁移：把 certifications 里 CET-4/6 的分数搬到 education（有分数才搬，不臆造）。
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, profile_id, name, score FROM certifications "
            "WHERE score IS NOT NULL AND score <> ''"
        )
    ).fetchall()
    for row in rows:
        name = (row.name or "").upper().replace(" ", "")
        if "CET-4" in name or "CET4" in name or "四级" in (row.name or ""):
            column = "cet4_score"
        elif "CET-6" in name or "CET6" in name or "六级" in (row.name or ""):
            column = "cet6_score"
        else:
            continue
        bind.execute(
            sa.text(
                f"UPDATE education SET {column} = :score "
                f"WHERE profile_id = :profile_id AND {column} IS NULL"
            ),
            {"score": row.score, "profile_id": row.profile_id},
        )


def downgrade() -> None:
    op.drop_index("ix_application_profiles_profile_id", table_name="application_profiles")
    op.drop_table("application_profiles")
    op.drop_column("education", "cet6_score")
    op.drop_column("education", "cet4_score")
