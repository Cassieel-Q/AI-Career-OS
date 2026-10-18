"""可信事实核对表：fact_attestations。

Revision ID: 028_trusted_facts
Revises: 027_application_binding

背景（可信求职闭环 v1.2 · Sprint A）：
系统此前把三件事混为一谈——「从简历里提取到了」「用户采纳了 AI 改写」「用户核实过事实」。
本迁移新增核对留痕表，只记录**用户明确核对**的行为：

- 没有本表记录的事实，即使档案状态是 CONFIRMED、改写状态是 ACCEPTED，
  也一律按 UNREVIEWED 处理（见 app.fact_trust.legacy_verification）。
- verified_at / verified_by 让「谁在什么时候确认的」可回溯。
- fact_key 与 profile_id 组成唯一键，事实变更后可判定是否需要重新核对。

只新增表，不改动任何既有表与列，向后兼容。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "028_trusted_facts"
down_revision: Union[str, None] = "027_application_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 测试里 Base.metadata.create_all 可能已经建好该表，这里保持幂等。
    if "fact_attestations" in _tables():
        return
    op.create_table(
        "fact_attestations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("fact_key", sa.String(length=200), nullable=False),
        sa.Column("fact_text", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("source_revision", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["user_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "fact_key", name="uq_fact_attestation_profile_key"),
    )
    op.create_index(op.f("ix_fact_attestations_profile_id"), "fact_attestations", ["profile_id"], unique=False)


def downgrade() -> None:
    if "fact_attestations" not in _tables():
        return
    with op.batch_alter_table("fact_attestations") as batch:
        batch.drop_index(batch.f("ix_fact_attestations_profile_id"))
    op.drop_table("fact_attestations")
