"""create profile confirmation tables

Revision ID: 001_create_profile_tables
Revises:
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "001_create_profile_tables"
down_revision = None
branch_labels = None
depends_on = None

STATUS_VALUES = "'DRAFT', 'CONFIRMED'"
SOURCE_VALUES = "'AI_EXTRACTED', 'USER_ENTERED', 'USER_EDITED'"
PROFICIENCY_VALUES = "'AWARE', 'BASIC', 'PROJECT_READY', 'PROFICIENT'"


def _child_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "profile_id",
            sa.Uuid(),
            sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
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
        sa.CheckConstraint(f"status IN ({STATUS_VALUES})", name="ck_user_profiles_status"),
    )

    education_columns = _child_columns()
    education_columns.extend(
        [
            sa.Column("institution", sa.String(length=255), nullable=False),
            sa.Column("degree", sa.String(length=255), nullable=True),
            sa.Column("field_of_study", sa.String(length=255), nullable=True),
            sa.Column("dates", sa.String(length=255), nullable=True),
            sa.CheckConstraint(f"source_type IN ({SOURCE_VALUES})", name="ck_education_source_type"),
            sa.CheckConstraint(
                "source_type = 'USER_ENTERED' OR evidence_text IS NOT NULL",
                name="ck_education_evidence_for_resume_source",
            ),
        ]
    )
    op.create_table("education", *education_columns)

    skill_columns = _child_columns()
    skill_columns.extend(
        [
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("proficiency", sa.String(length=32), nullable=True),
            sa.CheckConstraint(f"source_type IN ({SOURCE_VALUES})", name="ck_profile_skills_source_type"),
            sa.CheckConstraint(
                f"proficiency IS NULL OR proficiency IN ({PROFICIENCY_VALUES})",
                name="ck_profile_skills_proficiency",
            ),
            sa.CheckConstraint(
                "source_type = 'USER_ENTERED' OR evidence_text IS NOT NULL",
                name="ck_profile_skills_evidence_for_resume_source",
            ),
        ]
    )
    op.create_table("profile_skills", *skill_columns)

    experience_columns = _child_columns()
    experience_columns.extend(
        [
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("dates", sa.String(length=255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.CheckConstraint(f"source_type IN ({SOURCE_VALUES})", name="ck_experiences_source_type"),
            sa.CheckConstraint(
                "source_type = 'USER_ENTERED' OR evidence_text IS NOT NULL",
                name="ck_experiences_evidence_for_resume_source",
            ),
        ]
    )
    op.create_table("experiences", *experience_columns)

    certification_columns = _child_columns()
    certification_columns.extend(
        [
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("issuer", sa.String(length=255), nullable=True),
            sa.Column("date", sa.String(length=255), nullable=True),
            sa.CheckConstraint(f"source_type IN ({SOURCE_VALUES})", name="ck_certifications_source_type"),
            sa.CheckConstraint(
                "source_type = 'USER_ENTERED' OR evidence_text IS NOT NULL",
                name="ck_certifications_evidence_for_resume_source",
            ),
        ]
    )
    op.create_table("certifications", *certification_columns)

    for table in ("education", "profile_skills", "experiences", "certifications"):
        op.create_index(f"ix_{table}_profile_id", table, ["profile_id"])


def downgrade() -> None:
    for table in ("certifications", "experiences", "profile_skills", "education"):
        op.drop_index(f"ix_{table}_profile_id", table_name=table)
        op.drop_table(table)
    op.drop_table("user_profiles")
