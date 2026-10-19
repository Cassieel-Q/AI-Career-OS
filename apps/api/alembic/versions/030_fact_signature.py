"""fact_attestations 增加 signature_text：内部签名与展示文本分离（P1-B）。

Revision ID: 030_fact_signature
Revises: 029_delivery_snapshots

背景（FINAL FREEZE · P1-B）：
既有核对记录的 fact_text 只覆盖标题 / 组织 / 描述，**不含起止时间**。
结果：用户改了时间，旧的 USER_ATTESTED 仍在给新事实背书。

本迁移新增 ``signature_text`` 列存内部签名（覆盖标题、组织、起止时间、描述），
``fact_text`` 继续承担页面展示，两者职责分离：

- 新的核对动作同时写入 signature_text 与 fact_text。
- 旧记录（signature_text 为 NULL）按「展示文本仍一致」判定有效，
  并在判定时把当前签名补写进 signature_text（保守迁移：不批量升级、
  不把没有确认记录的字段自动升级为已核实）。
- 此后任何字段（含时间）变化都会使签名失配 → 退回 UNREVIEWED。

只加列，不删不改既有列，向后兼容。
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "030_fact_signature"
down_revision: Union[str, None] = "029_delivery_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    inspector = inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    # 测试里 Base.metadata.create_all 可能已按新模型建表，保持幂等。
    if "signature_text" in _columns("fact_attestations"):
        return
    with op.batch_alter_table("fact_attestations") as batch:
        batch.add_column(sa.Column("signature_text", sa.Text(), nullable=True))


def downgrade() -> None:
    if "signature_text" not in _columns("fact_attestations"):
        return
    with op.batch_alter_table("fact_attestations") as batch:
        batch.drop_column("signature_text")
