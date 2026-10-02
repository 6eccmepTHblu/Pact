"""Web Push и напоминания

Revision ID: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"

TS = sa.DateTime(timezone=True)


def upgrade():
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.String, nullable=False, unique=True),
        sa.Column("keys", JSONB, nullable=False),
    )
    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("law_id", sa.Integer, sa.ForeignKey("laws.id"), nullable=False, unique=True),
        sa.Column("next_fire_at", TS, nullable=False),
        sa.Column("snoozed_until", TS),
    )
