"""Нужна поднятая БД: docker compose up -d db migrate
Запуск из api/: uv run --env-file ../.env pytest
Всё выполняется в транзакциях с откатом, данные БД не меняются."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session


def _url(user: str, password_var: str) -> str:
    port = os.environ.get("DB_PORT", "5433")
    return f"postgresql+psycopg://{user}:{os.environ[password_var]}@127.0.0.1:{port}/pact"


os.environ.setdefault("DATABASE_URL", _url("pact_app", "APP_DB_PASSWORD"))

from app import journal  # noqa: E402

app_engine = create_engine(_url("pact_app", "APP_DB_PASSWORD"))
owner_engine = create_engine(_url("pact_owner", "POSTGRES_PASSWORD"))


def _session(engine):
    conn = engine.connect()
    conn.begin()
    return conn, Session(bind=conn)


def test_chain_ok_and_tamper_detected():
    conn, db = _session(owner_engine)
    try:
        a = journal.append(db, "test", payload={"n": 1, "текст": "ваза"})
        b = journal.append(db, "test", payload={"n": 2})
        assert b.prev_hash == a.hash
        assert journal.verify(db)["ok"]

        db.execute(text("UPDATE journal SET payload = '{\"n\": 99}' WHERE seq = :s"), {"s": a.seq})
        db.expire_all()
        result = journal.verify(db)
        assert not result["ok"] and result["bad_seq"] == a.seq
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize("sql", ["UPDATE journal SET action = 'x'", "DELETE FROM journal"])
def test_app_role_cannot_rewrite_journal(sql):
    conn, db = _session(app_engine)
    try:
        journal.append(db, "test")
        with pytest.raises(ProgrammingError, match="permission denied"):
            db.execute(text(sql))
    finally:
        conn.rollback()
        conn.close()
