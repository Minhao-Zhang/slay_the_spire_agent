"""Phase 1: backfill_jobs for logs/games import progress.

Revision ID: 0002_backfill
Revises: 0001_phase0
Create Date: 2026-04-17

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_backfill"
down_revision: Union[str, None] = "0001_phase0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_t = sa.JSON()
    op.create_table(
        "backfill_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_dir", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("rows_written_json", json_t, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_dir", name="uq_backfill_jobs_run_dir"),
    )


def downgrade() -> None:
    op.drop_table("backfill_jobs")
