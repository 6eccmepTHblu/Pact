"""Конвейер с подменённой LLM: от исходника до закона, правки → few-shot."""

import hashlib

import pytest
from sqlalchemy import select

from app import llm, pipeline
from app.models import EMBED_DIM, Correction

STROKES = {"width": 300, "height": 120, "strokes": [[[10, 60], [40, 20], [80, 90], [120, 40]]]}
VASE = "Хочу, чтобы цветы в вечной вазе всегда были свежими, проверяй каждый вечер"


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.rrule = "FREQ=DAILY"
        self.review = {"duplicates": [], "contradictions": [], "refs": []}

    def embed(self, texts):
        vecs = []
        for t in texts:
            v = [0.0] * EMBED_DIM
            v[int(hashlib.sha256(t.encode()).hexdigest(), 16) % EMBED_DIM] = 1.0
            v[0] += 0.5  # чтобы разные тексты не были ортогональны совсем
            vecs.append(v)
        return vecs

    def ask(self, system, examples, user, schema):
        self.calls.append((schema.__name__, examples, user))
        return {
            "ParseOut": lambda: schema(title="Следить за свежестью цветов в Вечной вазе", tags=["Цветы", "Ежедневно"],
                                       action="проверять и менять цветы", object="Вечная ваза",
                                       schedule={"rrule": self.rrule, "time": "19:00"}),
            "PlaceOut": lambda: schema(section="Цветы-т", article="Вечная ваза", is_new_section=True,
                                       is_new_article=True),
            "OfficialOut": lambda: schema(official_text="Супруг ежедневно проверяет цветы в Вечной вазе."),
            "CheckOut": lambda: schema(meaning_lost=False, comment=""),
            "ReviewOut": lambda: schema(**self.review),
        }[schema.__name__]()

    def last(self, name):
        return [c for c in self.calls if c[0] == name][-1]


@pytest.fixture
def fake(monkeypatch):
    f = FakeLLM()
    monkeypatch.setattr(llm, "embed", f.embed)
    monkeypatch.setattr(llm, "ask", f.ask)
    return f


def test_vase_from_wish_to_law(clients, fake):
    h, w, db = clients
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": VASE}))
    b = ok(h.post(f"/api/bills/{b['id']}/analyze"))
    p = b["prepared"]
    assert p["title"] == "Следить за свежестью цветов в Вечной вазе"
    assert p["placement"] == {"section": "Цветы-т", "article": "Вечная ваза"}
    assert p["schedule"] == {"rrule": "FREQ=DAILY", "time": "19:00"} and b["warnings"] == []

    # Супруг правит только текст → пример появляется лишь для этапа official
    edited = {**p, "official_text": "Супруг ежедневно в 19:00 проверяет цветы в Вечной вазе и меняет увядшие."}
    ok(h.put(f"/api/bills/{b['id']}/prepared", json={"original_text": VASE, "prepared": edited}))
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    stages = db.scalars(select(Correction.stage).where(Correction.bill_id == b["id"])).all()
    assert stages == ["official"]

    b = ok(w.post(f"/api/bills/{b['id']}/sign", json={**STROKES, "text_hash": b["text_hash"]}))
    law = ok(w.get(f"/api/laws/{b['law_id']}"))
    assert law["number"].endswith(".1.1") and law["versions"][0]["original_text"] == VASE

    # Следующий разбор: закон стал кандидатом места, правка — примером few-shot
    b2 = ok(h.post("/api/bills", json={"kind": "new", "original_text": "Розы в Вечной вазе — по пятницам"}))
    ok(h.post(f"/api/bills/{b2['id']}/analyze"))
    assert "статья «Вечная ваза»" in fake.last("PlaceOut")[2]
    examples = fake.last("OfficialOut")[1]
    assert len(examples) == 1 and "меняет увядшие" in examples[0][1]
    assert db.scalar(select(Correction.embedding).where(Correction.bill_id == b["id"])) is not None


def test_bad_schedule_dropped_with_warning(clients, fake):
    h, _, _ = clients
    fake.rrule = "каждый день"
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": VASE}))
    b = ok(h.post(f"/api/bills/{b['id']}/analyze"))
    assert b["prepared"]["schedule"] is None
    assert any("Расписание не распознано" in x for x in b["warnings"])


def test_amend_keeps_place_and_sees_current_text(clients, fake):
    h, w, _ = clients
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": VASE}))
    ok(h.post(f"/api/bills/{b['id']}/analyze"))
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    law_id = ok(w.post(f"/api/bills/{b['id']}/sign", json={**STROKES, "text_hash": b["text_hash"]}))["law_id"]

    a = ok(h.post("/api/bills", json={"kind": "amend", "target_law_id": law_id, "original_text": "по утрам"}))
    a = ok(h.post(f"/api/bills/{a['id']}/analyze"))
    assert a["prepared"]["placement"] is None
    assert "Действующий закон" in fake.last("OfficialOut")[2]
    assert not [c for c in fake.calls[-4:] if c[0] == "PlaceOut"]


def test_no_api_key_is_clear_error(clients, monkeypatch):
    h, _, _ = clients
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": VASE}))
    assert "API-ключ" in ok(h.post(f"/api/bills/{b['id']}/analyze"), 503)["detail"]


def enact(h, w, text):
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": text}))
    ok(h.post(f"/api/bills/{b['id']}/analyze"))
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    b = ok(w.post(f"/api/bills/{b['id']}/sign", json={**STROKES, "text_hash": b["text_hash"]}))
    return ok(w.get(f"/api/laws/{b['law_id']}"))


def test_review_duplicates_and_refs(clients, fake):
    h, w, _ = clients
    a = enact(h, w, VASE)

    fake.review = {"duplicates": [{"number": a["number"], "comment": "то же самое"}],
                   "contradictions": [{"number": "9.9.9", "comment": "выдуманный номер"}],
                   "refs": [a["number"], a["number"], "9.9.9"]}
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": "Менять воду в Вечной вазе"}))
    b = ok(h.post(f"/api/bills/{b['id']}/analyze"))
    assert a["number"] in fake.last("ReviewOut")[2]
    assert b["warnings"] == [f"Возможный дубль {a['number']} «{a['versions'][0]['title']}»: то же самое"]
    assert b["prepared"]["refs"] == [a["id"]] and b["refs"][0]["number"] == a["number"]

    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    law_b = ok(w.get(f"/api/laws/{ok(w.post(f'/api/bills/{b['id']}/sign', json={**STROKES, 'text_hash': b['text_hash']}))['law_id']}"))
    assert [r["id"] for r in law_b["refs"]] == [a["id"]]
    assert [r["id"] for r in ok(w.get(f"/api/laws/{a['id']}"))["referenced_by"]] == [law_b["id"]]

    # Упразднение показывает зависимые законы; правка сохраняет ссылки
    r = ok(h.post("/api/bills", json={"kind": "repeal", "target_law_id": a["id"], "original_text": "не нужен"}))
    assert [x["id"] for x in r["target"]["referenced_by"]] == [law_b["id"]]
    fake.review = {"duplicates": [], "contradictions": [], "refs": []}
    m = ok(h.post("/api/bills", json={"kind": "amend", "target_law_id": law_b["id"], "original_text": "чаще"}))
    assert m["prepared"]["refs"] == [a["id"]]
    assert ok(h.post(f"/api/bills/{m['id']}/analyze"))["prepared"]["refs"] == [a["id"]]

    # Ссылка на несуществующий закон не пройдёт отправку
    bad = {**m["prepared"], "refs": [999999]}
    ok(h.put(f"/api/bills/{m['id']}/prepared", json={"original_text": "чаще", "prepared": bad}))
    ok(h.post(f"/api/bills/{m['id']}/submit"), 422)
