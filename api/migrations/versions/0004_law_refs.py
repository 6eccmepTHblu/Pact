"""Перекрёстные ссылки законов

Revision ID: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.create_table(
        "law_refs",
        sa.Column("from_law_id", sa.Integer, sa.ForeignKey("laws.id"), primary_key=True),
        sa.Column("to_law_id", sa.Integer, sa.ForeignKey("laws.id"), primary_key=True),
        sa.CheckConstraint("from_law_id <> to_law_id"),
    )
