"""Нужна поднятая БД: docker compose up -d db migrate
Запуск из api/: uv run --env-file ../.env pytest
Всё выполняется в транзакциях с откатом, данные БД не меняются."""

import os

import pytest
from sqlalchemy import create_engine


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
