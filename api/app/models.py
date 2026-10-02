from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('husband', 'wife')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    role: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]


class Journal(Base):
    __tablename__ = "journal"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    entity: Mapped[str | None]
    payload: Mapped[dict] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


TS = DateTime(timezone=True)


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(unique=True)
    title: Mapped[str] = mapped_column(unique=True)


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (UniqueConstraint("section_id", "number"), UniqueConstraint("section_id", "title"))

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    number: Mapped[int]
    title: Mapped[str]


class Law(Base):
    __tablename__ = "laws"
    __table_args__ = (UniqueConstraint("article_id", "number"),
                      CheckConstraint("status IN ('active', 'repealed')"))

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    number: Mapped[int]
    status: Mapped[str] = mapped_column(default="active")
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("law_versions.id", use_alter=True))
    enacted_at: Mapped[datetime] = mapped_column(TS)
    repealed_at: Mapped[datetime | None] = mapped_column(TS)


class LawVersion(Base):
    __tablename__ = "law_versions"
    __table_args__ = (UniqueConstraint("law_id", "version_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    law_id: Mapped[int] = mapped_column(ForeignKey("laws.id"))
    version_no: Mapped[int]
    title: Mapped[str]
    official_text: Mapped[str]
    original_text: Mapped[str]
    tags: Mapped[list] = mapped_column(JSONB)
    schedule: Mapped[dict | None] = mapped_column(JSONB)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))
    signed_at: Mapped[datetime] = mapped_column(TS)


BILL_KINDS = ("new", "amend", "repeal")
# request и rejected — заявки супруги, этап 5
BILL_STATUSES = ("request", "rejected", "draft", "pending", "returned", "partial", "enacted", "withdrawn")


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (CheckConstraint(f"kind IN {BILL_KINDS}"), CheckConstraint(f"status IN {BILL_STATUSES}"))

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str]
    target_law_id: Mapped[int | None] = mapped_column(ForeignKey("laws.id"))
    status: Mapped[str]
    original_text: Mapped[str]
    llm_result: Mapped[dict | None] = mapped_column(JSONB)
    prepared: Mapped[dict | None] = mapped_column(JSONB)
    wife_comment: Mapped[str | None]
    reject_reason: Mapped[str | None]
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


class Signature(Base):
    __tablename__ = "signatures"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    strokes: Mapped[dict] = mapped_column(JSONB)
    svg: Mapped[str]
    svg_hash: Mapped[str] = mapped_column(String(64))
    text_hash: Mapped[str] = mapped_column(String(64))
    signed_at: Mapped[datetime] = mapped_column(TS)


EMBED_DIM = 1536  # text-embedding-3-small; другая модель с иной размерностью — новая миграция


class VersionEmbedding(Base):
    """Эмбеддинг редакции закона. Отдельно от law_versions: те неизменяемы, а эмбеддинги пересчитываются."""
    __tablename__ = "version_embeddings"

    version_id: Mapped[int] = mapped_column(ForeignKey("law_versions.id"), primary_key=True)
    embedding = mapped_column(Vector(EMBED_DIM), nullable=False)


class Correction(Base):
    """Пара «предложение LLM → итог супруга» для few-shot."""
    __tablename__ = "corrections"
    __table_args__ = (UniqueConstraint("bill_id", "stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))
    stage: Mapped[str]
    input: Mapped[str]
    llm_output: Mapped[dict] = mapped_column(JSONB)
    final: Mapped[dict] = mapped_column(JSONB)
    embedding = mapped_column(Vector(EMBED_DIM))
