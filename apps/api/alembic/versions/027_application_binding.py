"""投递版本绑定 + 打招呼话术：job_applications 补六列。

Revision ID: 027_application_binding
Revises: 026_webform_and_ingest

背景（M3 求职管理补齐）：
- 投递记录必须能回答「我当初投的是哪份简历」：
  绑定岗位定向简历版本（resume_version_id）+ Studio 修订号（studio_revision）
  + PDF 快照文件（pdf_snapshot_path）。
- 打招呼话术：系统生成草稿（简洁版/详细版），用户可编辑；不自动发送。
- jd_source 记录 JD 从哪来（URL 或「粘贴」）。

全部可空，向后兼容。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "027_application_binding"
down_revision: Union[str, None] = "026_webform_and_ingest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if "job_applications" in _tables():
        additions = [
            ("jd_source", sa.Column("jd_source", sa.String(512), nullable=True)),
            ("resume_version_id", sa.Column("resume_version_id", sa.Uuid(), nullable=True)),
            ("studio_revision", sa.Column("studio_revision", sa.Integer(), nullable=True)),
            ("pdf_snapshot_path", sa.Column("pdf_snapshot_path", sa.String(512), nullable=True)),
            ("greeting_short", sa.Column("greeting_short", sa.Text(), nullable=True)),
            ("greeting_long", sa.Column("greeting_long", sa.Text(), nullable=True)),
        ]
        for name, column in additions:
            if not _has_column("job_applications", name):
                op.add_column("job_applications", column)


def downgrade() -> None:
    if "job_applications" in _tables():
        for name in ("greeting_long", "greeting_short", "pdf_snapshot_path", "studio_revision", "resume_version_id", "jd_source"):
            if _has_column("job_applications", name):
                op.drop_column("job_applications", name)
