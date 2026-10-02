"""Ядро Пакта: разделы, статьи, законы, редакции, законопроекты, подписи

Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.models import BILL_KINDS, BILL_STATUSES

revision = "0002"
down_revision = "0001"

TS = sa.DateTime(timezone=True)


def upgrade():
    op.create_table(
        "sections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("number", sa.Integer, nullable=False, unique=True),
        sa.Column("title", sa.String, nullable=False, unique=True),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("section_id", sa.Integer, sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.UniqueConstraint("section_id", "number"),
        sa.UniqueConstraint("section_id", "title"),
    )
    op.create_table(
        "laws",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("article_id", sa.Integer, sa.ForeignKey("articles.id"), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("current_version_id", sa.Integer),
        sa.Column("enacted_at", TS, nullable=False),
        sa.Column("repealed_at", TS),
        sa.UniqueConstraint("article_id", "number"),
        sa.CheckConstraint("status IN ('active', 'repealed')"),
    )
    op.create_table(
        "bills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("target_law_id", sa.Integer, sa.ForeignKey("laws.id")),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("original_text", sa.String, nullable=False),
        sa.Column("llm_result", JSONB),
        sa.Column("prepared", JSONB),
        sa.Column("wife_comment", sa.String),
        sa.Column("reject_reason", sa.String),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"kind IN {BILL_KINDS}"),
        sa.CheckConstraint(f"status IN {BILL_STATUSES}"),
    )
    op.create_table(
        "law_versions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("law_id", sa.Integer, sa.ForeignKey("laws.id"), nullable=False),
        sa.Column("version_no", sa.Integer, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("official_text", sa.String, nullable=False),
        sa.Column("original_text", sa.String, nullable=False),
        sa.Column("tags", JSONB, nullable=False),
        sa.Column("schedule", JSONB),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("bills.id"), nullable=False),
        sa.Column("signed_at", TS, nullable=False),
        sa.UniqueConstraint("law_id", "version_no"),
    )
    op.create_foreign_key("laws_current_version_fk", "laws", "law_versions", ["current_version_id"], ["id"])
    op.create_table(
        "signatures",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("bills.id"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("strokes", JSONB, nullable=False),
        sa.Column("svg", sa.String, nullable=False),
        sa.Column("svg_hash", sa.String(64), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("signed_at", TS, nullable=False),
    )
    # Подписи и редакции — история: роль приложения только читает и добавляет.
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON signatures, law_versions FROM pact_app")
    # Разделы, статьи и законы не удаляются никогда (упразднение — это UPDATE статуса).
    op.execute("REVOKE DELETE, TRUNCATE ON sections, articles, laws FROM pact_app")
