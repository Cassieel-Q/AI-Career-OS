"""岗位来源元数据 + 网申填表历史表。

Revision ID: 026_webform_and_ingest
Revises: 025_job_insight

背景：
- 「岗位统一入口」要显示来源 URL / 采集时间 / 解析状态，并在候选岗位库里去重，
  因此给 candidate_jobs 补四列（全部可空，向后兼容）。
- 「网申填表」需要记录每次填写历史（成功/失败/待确认数量与原因），新增 web_form_records。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "026_webform_and_ingest"
down_revision: Union[str, None] = "025_job_insight"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if "candidate_jobs" in _tables():
        if not _has_column("candidate_jobs", "source_url"):
            op.add_column("candidate_jobs", sa.Column("source_url", sa.String(1024), nullable=True))
        if not _has_column("candidate_jobs", "collected_at"):
            op.add_column("candidate_jobs", sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_column("candidate_jobs", "parse_status"):
            op.add_column(
                "candidate_jobs",
                sa.Column("parse_status", sa.String(32), nullable=False, server_default="PARSED"),
            )
        if not _has_column("candidate_jobs", "dedupe_key"):
            op.add_column("candidate_jobs", sa.Column("dedupe_key", sa.String(64), nullable=True))
            op.create_index("ix_candidate_jobs_dedupe_key", "candidate_jobs", ["dedupe_key"])

    if "web_form_records" not in _tables():
        op.create_table(
            "web_form_records",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column(
                "profile_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("user_profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("page_url", sa.String(1024), nullable=False, server_default=""),
            sa.Column("page_title", sa.String(512), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="PREVIEW"),
            sa.Column("assignments", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_web_form_records_profile_id", "web_form_records", ["profile_id"])


def downgrade() -> None:
    if "web_form_records" in _tables():
        op.drop_index("ix_web_form_records_profile_id", table_name="web_form_records")
        op.drop_table("web_form_records")
    if "candidate_jobs" in _tables():
        if _has_column("candidate_jobs", "dedupe_key"):
            op.drop_index("ix_candidate_jobs_dedupe_key", table_name="candidate_jobs")
            op.drop_column("candidate_jobs", "dedupe_key")
        for column in ("parse_status", "collected_at", "source_url"):
            if _has_column("candidate_jobs", column):
                op.drop_column("candidate_jobs", column)
