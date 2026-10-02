"""LLM: эмбеддинги редакций и примеры правок

Revision ID: 0003
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

from app.models import EMBED_DIM

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "version_embeddings",
        sa.Column("version_id", sa.Integer, sa.ForeignKey("law_versions.id"), primary_key=True),
        sa.Column("embedding", Vector(EMBED_DIM), nullable=False),
    )
    op.create_table(
        "corrections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("bill_id", sa.Integer, sa.ForeignKey("bills.id"), nullable=False),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("input", sa.String, nullable=False),
        sa.Column("llm_output", JSONB, nullable=False),
        sa.Column("final", JSONB, nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM)),
        sa.UniqueConstraint("bill_id", "stage"),
    )
