"""Спросить Пакт: только действующие законы, только реальные номера, без ссылок — «ничего не сказано»."""

import pytest

from app import ask, llm
from app.models import EMBED_DIM

STROKES = {"width": 300, "height": 120, "strokes": [[[10, 60], [40, 20], [80, 90], [120, 40]]]}


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def enact(h, w, title):
    prepared = {"title": title, "official_text": f"Супруг обязан: {title}.", "tags": [],
                "placement": {"section": "Спрос-т", "article": "Разное"}}
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": title, "prepared": prepared}))
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    b = ok(w.post(f"/api/bills/{b['id']}/sign", json={**STROKES, "text_hash": b["text_hash"]}))
    return ok(w.get(f"/api/laws/{b['law_id']}"))


@pytest.fixture
def fake(monkeypatch):
    state = {"reply": None, "prompts": []}
    monkeypatch.setattr(llm, "embed", lambda texts, cfg=None: [[1.0] * EMBED_DIM for _ in texts])

    def fake_ask(system, examples, user, schema, cfg=None):
        state["prompts"].append(user)
        return schema(**state["reply"](user))

    monkeypatch.setattr(llm, "ask", fake_ask)
    return state


def test_ask(clients, fake):
    h, w, _ = clients
    ficus = enact(h, w, "Поливать фикус")
    gone = enact(h, w, "Кормить попугая")
    r = ok(h.post("/api/bills", json={"kind": "repeal", "target_law_id": gone["id"], "original_text": "улетел"}))
    r = ok(h.post(f"/api/bills/{r['id']}/sign", json={**STROKES, "text_hash": r["text_hash"]}))
    ok(w.post(f"/api/bills/{r['id']}/sign", json={**STROKES, "text_hash": r["text_hash"]}))

    n = ficus["number"]
    fake["reply"] = lambda user: {"found": True, "answer": f"Супруг поливает фикус [{n}], а ещё летает [9.9.9]."}
    res = ok(w.post("/api/ask", json={"question": "что там про фикус?"}))
    assert f"[{n}] Поливать фикус" in fake["prompts"][-1]
    assert gone["number"] not in fake["prompts"][-1]  # упразднённый закон в контекст не попадает
    assert res["answer"] == f"Супруг поливает фикус [{n}], а ещё летает."
    assert res["laws"] == [{"id": ficus["id"], "number": n, "title": "Поливать фикус"}]

    fake["reply"] = lambda user: {"found": False, "answer": "Наверное, нельзя."}
    assert ok(h.post("/api/ask", json={"question": "про слонов?"})) == {"answer": ask.NOT_FOUND, "laws": []}

    fake["reply"] = lambda user: {"found": True, "answer": "Можно, если очень хочется."}  # без ссылок — догадка
    assert ok(h.post("/api/ask", json={"question": "а можно?"}))["answer"] == ask.NOT_FOUND
