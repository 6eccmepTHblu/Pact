import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app import journal


def _session(engine):
    conn = engine.connect()
    conn.begin()
    return conn, Session(bind=conn)


def test_chain_ok_and_tamper_detected(owner_engine):
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


@pytest.mark.parametrize("sql", [
    "UPDATE journal SET action = 'x'", "DELETE FROM journal",
    "UPDATE signatures SET svg = ''", "DELETE FROM law_versions", "DELETE FROM laws",
])
def test_app_role_cannot_rewrite_history(app_engine, sql):
    conn, db = _session(app_engine)
    try:
        with pytest.raises(ProgrammingError, match="permission denied"):
            db.execute(text(sql))
    finally:
        conn.rollback()
        conn.close()
