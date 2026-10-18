"""投递版本快照表：delivery_snapshots。

Revision ID: 029_delivery_snapshots
Revises: 028_trusted_facts

背景（可信求职闭环 v1.2 · Sprint E）：
面试准备此前默认读取「最新 Studio 修订版」，会把投递之后才新增的经历当成面试官
已经看到的简历内容。要回答「我当初投的是哪份简历」，只靠 ``ResumeStudioDocument``
不够——它只保存最新 ``document_json``，历史修订会被覆盖。

本迁移新增不可变快照表，记录每一次「用户确认的正式投递版」：

- ``document_json``：投递当时的完整正文，之后 Studio 再改也不影响；
- ``content_hash``：可校验副本，用于证明快照未被改写；
- ``pdf_path``：投递当时的 PDF 文件（与 document_json 同一次渲染）；
- ``source``：STUDIO_CONFIRM（用户确认修订版）/ APPLICATION_BIND（绑定投递记录）。

只新增表，不改动既有表与列，向后兼容。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "029_delivery_snapshots"
down_revision: Union[str, None] = "028_trusted_facts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "delivery_snapshots" in _tables():
        return
    op.create_table(
        "delivery_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("mission_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=True),
        sa.Column("studio_revision", sa.Integer(), nullable=False),
        sa.Column("document_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("pdf_path", sa.String(length=512), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mission_id"], ["job_missions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_delivery_snapshots_profile_id"), "delivery_snapshots", ["profile_id"], unique=False)
    op.create_index(op.f("ix_delivery_snapshots_mission_id"), "delivery_snapshots", ["mission_id"], unique=False)
    op.create_index(op.f("ix_delivery_snapshots_application_id"), "delivery_snapshots", ["application_id"], unique=False)


def downgrade() -> None:
    if "delivery_snapshots" not in _tables():
        return
    with op.batch_alter_table("delivery_snapshots") as batch:
        batch.drop_index(batch.f("ix_delivery_snapshots_profile_id"))
        batch.drop_index(batch.f("ix_delivery_snapshots_mission_id"))
        batch.drop_index(batch.f("ix_delivery_snapshots_application_id"))
    op.drop_table("delivery_snapshots")
