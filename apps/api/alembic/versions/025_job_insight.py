"""Add JobMission.analysis / match_analysis + UserProfile.resume_text.

Revision ID: 025_job_insight
Revises: 024_interview_agent

背景：
- 「准备度」原来只是 workflow_state 的固定映射，与简历无关；岗位表格也没有岗位特征。
  新增两列缓存「岗位关键词分析」与「简历×岗位匹配度」的模型输出，避免每次进列表都调模型。
- 简历中心要在「简历工作台」里直接编辑简历原始文字，因此新增 UserProfile.resume_text。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "025_job_insight"
down_revision: Union[str, None] = "024_interview_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def _json_type() -> sa.types.TypeEngine:
    """SQLite 不支持 JSONB，按方言选择类型（demo 用 SQLite，生产用 Postgres）。"""
    try:
        if op.get_bind().dialect.name == "postgresql":
            return postgresql.JSONB(astext_type=sa.Text())
    except Exception:  # noqa: BLE001
        pass
    return sa.JSON()


def upgrade() -> None:
    if not _has_column("job_missions", "analysis"):
        op.add_column("job_missions", sa.Column("analysis", _json_type(), nullable=True))
    if not _has_column("job_missions", "match_analysis"):
        op.add_column("job_missions", sa.Column("match_analysis", _json_type(), nullable=True))
    if not _has_column("user_profiles", "resume_text"):
        op.add_column("user_profiles", sa.Column("resume_text", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("user_profiles", "resume_text"):
        op.drop_column("user_profiles", "resume_text")
    if _has_column("job_missions", "match_analysis"):
        op.drop_column("job_missions", "match_analysis")
    if _has_column("job_missions", "analysis"):
        op.drop_column("job_missions", "analysis")
