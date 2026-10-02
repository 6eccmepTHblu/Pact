"""Нужна поднятая БД: docker compose up -d db migrate
Запуск из api/: uv run --env-file ../.env pytest
Всё выполняется в транзакциях с откатом, данные БД не меняются."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _url(user: str, password_var: str) -> str:
    port = os.environ.get("DB_PORT", "5433")
    return f"postgresql+psycopg://{user}:{os.environ[password_var]}@127.0.0.1:{port}/pact"


os.environ.setdefault("DATABASE_URL", _url("pact_app", "APP_DB_PASSWORD"))
os.environ["COOKIE_SECURE"] = "false"


@pytest.fixture(scope="session")
def app_engine():
    return create_engine(_url("pact_app", "APP_DB_PASSWORD"))


@pytest.fixture(scope="session")
def owner_engine():
    return create_engine(_url("pact_owner", "POSTGRES_PASSWORD"))


@pytest.fixture
def clients(app_engine):
    from app.db import get_db
    from app.main import app

    conn = app_engine.connect()
    outer = conn.begin()
    # commit() внутри эндпоинтов закрывает лишь savepoint, внешняя транзакция откатывается
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    app.dependency_overrides[get_db] = lambda: db
    result = {}
    for role in ("husband", "wife"):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"login": os.environ[f"{role.upper()}_LOGIN"],
                                            "password": os.environ[f"{role.upper()}_PASSWORD"]})
        assert r.status_code == 200, r.text
        result[role] = c
    yield result["husband"], result["wife"], db
    app.dependency_overrides.clear()
    db.close()
    outer.rollback()
    conn.close()
