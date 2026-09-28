"""Add JobMission.workflow_state + resume_source.

Revision ID: 012_workflow_state
Revises: 011_evidence_os
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "012_workflow_state"
down_revision: Union[str, None] = "011_evidence_os"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = {c["name"] for c in inspect(bind).get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_column("job_missions", "workflow_state"):
        op.add_column(
            "job_missions",
            sa.Column("workflow_state", sa.String(length=64), nullable=False, server_default="ROLE_UNDERSTOOD"),
        )
    if not _has_column("job_missions", "resume_source"):
        # Prefer portable JSON; fall back to JSONB dialect when available.
        try:
            json_type = postgresql.JSONB(astext_type=sa.Text())
        except Exception:
            json_type = sa.JSON()
        op.add_column("job_missions", sa.Column("resume_source", json_type, nullable=True))
    # Best-effort backfill from coarse status for existing rows
    op.execute(
        """
        UPDATE job_missions
        SET workflow_state = CASE
          WHEN status = 'COMPLETED' THEN 'OUTCOME'
          WHEN status = 'INTERVIEWING' THEN 'INTERVIEW_IN_PROGRESS'
          WHEN status = 'INTERVIEW_PREP' THEN 'INTERVIEW_PREP_READY'
          WHEN status = 'STRENGTHENING' THEN 'STRENGTHENING_REQUIRED'
          WHEN status = 'RESUME_PREP' THEN 'RESUME_STRATEGY_REQUIRED'
          ELSE COALESCE(workflow_state, 'ROLE_UNDERSTOOD')
        END
        WHERE workflow_state IS NULL OR workflow_state = 'ROLE_UNDERSTOOD'
        """
    )


def downgrade() -> None:
    if _has_column("job_missions", "resume_source"):
        op.drop_column("job_missions", "resume_source")
    if _has_column("job_missions", "workflow_state"):
        op.drop_column("job_missions", "workflow_state")
