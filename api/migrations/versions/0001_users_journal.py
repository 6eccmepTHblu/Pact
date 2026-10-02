"""users и journal

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("login", sa.String, nullable=False, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("role", sa.String, nullable=False, unique=True),
        sa.Column("password_hash", sa.String, nullable=False),
        sa.CheckConstraint("role IN ('husband', 'wife')"),
    )
    op.create_table(
        "journal",
        sa.Column("seq", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("entity", sa.String),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    # Права по умолчанию из db/init.sh дают роли приложения всё; журнал — только чтение и добавление.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON journal FROM pact_app")
