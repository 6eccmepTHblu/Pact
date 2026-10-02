"""Настройки LLM: выбор провайдера и моделей, ключ не утекает, проверка соединения, сброс индекса."""

from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select

from app import llm
from app.models import EMBED_DIM, LawVersion, VersionEmbedding


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


class FakeProvider:
    """Минимальный двойник openai.OpenAI: Gemini отдаёт id с префиксом models/ и 3072 измерения."""

    def __init__(self):
        self.models = NS(list=lambda: [NS(id=f"models/{i}") for i in (
            "gemini-3.8-flash", "gemini-embedding-001", "imagen-4", "gemini-2.5-flash-preview-tts")])
        self.embeddings = NS(create=lambda model, input: NS(data=[NS(embedding=[0.1] * 3072) for _ in input]))
        self.chat = NS(completions=NS(parse=self.parse))
        self.seen = []

    def parse(self, model, messages, response_format, temperature):
        self.seen.append(model)
        return NS(choices=[NS(message=NS(parsed=response_format(ok=True), refusal=None))])


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(llm, "_client", lambda cfg: fake)
    return fake


def test_llm_settings(clients, provider):
    h, w, db = clients
    ok(w.get("/api/settings/llm"), 403)
    s = ok(h.get("/api/settings/llm"))
    assert {p["id"] for p in s["providers"]} == {"openai", "gemini"}

    probe = {"provider": "gemini", "api_key": "AIza-secret-1234"}
    m = ok(h.post("/api/settings/llm/models", json=probe))
    assert m == {"chat": ["gemini-3.8-flash"], "embed": ["gemini-embedding-001"]}

    t = ok(h.post("/api/settings/llm/test", json={**probe, "chat_model": "gemini-3.8-flash",
                                                  "embed_model": "gemini-embedding-001"}))
    assert t["chat"]["ok"] and t["embed"] == {**t["embed"], "ok": True, "dims": 3072}
    assert provider.seen[-1] == "gemini-3.8-flash"

    # Сохранение: ключ не возвращается, только маска; смена модели эмбеддингов сбрасывает индекс
    version_id = db.scalar(select(LawVersion.id).limit(1))
    if version_id:
        db.merge(VersionEmbedding(version_id=version_id, embedding=[0.1] * EMBED_DIM))
    saved = ok(h.put("/api/settings/llm", json={**probe, "chat_model": "gemini-3.8-flash",
                                                "embed_model": "gemini-embedding-001"}))
    assert saved["provider"] == "gemini" and saved["reindex"] is True
    assert saved["keys"]["gemini"] == "…1234" and "AIza-secret" not in str(saved)
    assert db.scalar(select(func.count()).select_from(VersionEmbedding)) == 0

    # Повторное сохранение без ключа: ключ остаётся, индекс не трогается
    again = ok(h.put("/api/settings/llm", json={"provider": "gemini", "chat_model": "gemini-3.8-flash",
                                                "embed_model": "gemini-embedding-001"}))
    assert again["keys"]["gemini"] == "…1234" and again["reindex"] is False
    assert llm.config(db=db)["api_key"] == "AIza-secret-1234"

    # Эмбеддинги усекаются до размерности колонки
    assert len(llm.embed(["x"], llm.config(db=db))[0]) == EMBED_DIM
