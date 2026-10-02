"""Заявки супруги, уведомления, напоминания, ICS."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import main, push, reminders
from app.models import PushSubscription, Reminder

STROKES = {"width": 300, "height": 120, "strokes": [[[10, 60], [40, 20], [80, 90], [120, 40]]]}
PREPARED = {"title": "Поливать фикус", "official_text": "Супруг поливает фикус по вечерам.", "tags": ["Быт"],
            "schedule": {"rrule": "FREQ=DAILY", "time": "19:00"},
            "placement": {"section": "Быт-т", "article": "Фикус"}}


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


@pytest.fixture
def sent(monkeypatch):
    calls = []
    monkeypatch.setattr(push, "notify", lambda bg, roles, title, body="", url="/": calls.append((roles, title)))
    return calls


def enact(h, w, prepared=PREPARED):
    b = ok(h.post("/api/bills", json={"kind": "new", "original_text": "фикус", "prepared": prepared}))
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    b = ok(w.post(f"/api/bills/{b['id']}/sign", json={**STROKES, "text_hash": b["text_hash"]}))
    return b["law_id"]


def test_wife_requests(clients, sent):
    h, w, _ = clients
    r = ok(w.post("/api/bills", json={"kind": "new", "original_text": "Хочу, чтобы фикус поливали",
                                      "prepared": PREPARED}))
    assert r["status"] == "request" and r["mine"] and r["prepared"] is None  # разметку супруга не задаёт
    assert sent[-1] == (["husband"], "Подана заявка")
    ok(w.post(f"/api/bills/{r['id']}/accept"), 403)
    ok(h.post(f"/api/bills/{r['id']}/submit"), 409)  # сначала взять в работу

    r = ok(h.post(f"/api/bills/{r['id']}/accept"))
    assert r["status"] == "draft"
    ok(h.put(f"/api/bills/{r['id']}/prepared", json={"original_text": r["original_text"], "prepared": PREPARED}))
    mine = ok(w.get(f"/api/bills/{r['id']}"))  # своя заявка видна, черновая разметка — нет
    assert mine["status"] == "draft" and mine["prepared"] is None and mine["title"].startswith("Хочу")
    assert r["id"] in [b["id"] for b in ok(w.get("/api/bills"))]

    x = ok(w.post("/api/bills", json={"kind": "new", "original_text": "Купить слона"}))
    x = ok(h.post(f"/api/bills/{x['id']}/reject", json={"comment": "Слон не влезет"}))
    assert ok(w.get(f"/api/bills/{x['id']}"))["reject_reason"] == "Слон не влезет"
    assert sent[-1] == (["wife"], "Заявка отклонена")

    # Заявка на упразднение: супруг принимает и подписывает первым, супруга — второй
    law_id = enact(h, w)
    assert sent[-1] == (["husband", "wife"], "Закон вступил в силу")
    rp = ok(w.post("/api/bills", json={"kind": "repeal", "target_law_id": law_id, "original_text": "фикус засох"}))
    rp = ok(h.post(f"/api/bills/{rp['id']}/accept"))
    rp = ok(h.post(f"/api/bills/{rp['id']}/sign", json={**STROKES, "text_hash": rp["text_hash"]}))
    assert rp["status"] == "partial" and sent[-1] == (["wife"], "Упразднение ждёт подписи")
    ok(w.post(f"/api/bills/{rp['id']}/sign", json={**STROKES, "text_hash": rp["text_hash"]}))
    assert ok(w.get(f"/api/laws/{law_id}"))["status"] == "repealed"

    # Заявка на правку: после принятия черновик начинается с действующей редакции
    law2 = enact(h, w)
    am = ok(w.post("/api/bills", json={"kind": "amend", "target_law_id": law2, "original_text": "по утрам"}))
    assert ok(h.post(f"/api/bills/{am['id']}/accept"))["prepared"]["title"] == "Поливать фикус"


def test_next_fire():
    start = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # 15:00 МСК, четверг
    msk = reminders.TZ
    nf = lambda rrule, after: reminders.next_fire({"rrule": rrule, "time": "19:00"}, start, after).astimezone(msk)
    assert nf("FREQ=DAILY", start) == datetime(2026, 10, 1, 19, 0, tzinfo=msk)
    assert nf("FREQ=DAILY", datetime(2026, 10, 1, 16, 1, tzinfo=UTC)) == datetime(2026, 10, 2, 19, 0, tzinfo=msk)
    assert nf("FREQ=WEEKLY;BYDAY=MO", start) == datetime(2026, 10, 5, 19, 0, tzinfo=msk)
    assert nf("FREQ=MONTHLY;BYMONTHDAY=15", start) == datetime(2026, 10, 15, 19, 0, tzinfo=msk)


def test_reminders_done_snooze_and_ics(clients, sent, monkeypatch):
    h, w, db = clients
    law_id = enact(h, w)
    r = db.scalar(select(Reminder).where(Reminder.law_id == law_id))
    fire = r.next_fire_at
    assert fire.astimezone(reminders.TZ).strftime("%H:%M") == "19:00" and fire > datetime.now(UTC)

    out = []
    send = lambda roles, p: out.append((roles, p))
    assert reminders.tick(db, fire - timedelta(minutes=1), send) == 0
    assert reminders.tick(db, fire + timedelta(seconds=30), send) == 1
    roles, p = out[-1]
    assert roles == ["husband"] and p["law_id"] == law_id and [a["action"] for a in p["actions"]] == ["done", "snooze"]
    db.refresh(r)
    assert r.next_fire_at == fire + timedelta(days=1)

    # Отложить: сработает через час от текущего момента, а не по расписанию
    ok(w.post(f"/api/laws/{law_id}/snooze"), 403)
    until = datetime.fromisoformat(ok(h.post(f"/api/laws/{law_id}/snooze"))["until"])
    assert reminders.tick(db, until - timedelta(minutes=1), send) == 0
    assert reminders.tick(db, until + timedelta(seconds=1), send) == 1
    db.refresh(r)
    assert r.snoozed_until is None and r.next_fire_at == fire + timedelta(days=1)

    ok(h.post(f"/api/laws/{law_id}/done"))
    assert len(ok(w.get(f"/api/laws/{law_id}"))["done"]) == 1

    # ICS: событие с расписанием, строки по RFC не длиннее 75 октетов, чужой токен — 404
    monkeypatch.setattr(main, "CALENDAR_TOKEN", "tok")
    ok(h.get("/calendar/nope.ics"), 404)
    r_ics = h.get("/calendar/tok.ics")
    assert r_ics.status_code == 200 and r_ics.headers["content-type"].startswith("text/calendar")
    text = r_ics.text
    assert f"UID:pact-law-{law_id}@pact" in text and "RRULE:FREQ=DAILY" in text and "T190000" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))

    # Упразднение снимает напоминание
    rp = ok(h.post("/api/bills", json={"kind": "repeal", "target_law_id": law_id, "original_text": "всё"}))
    rp = ok(h.post(f"/api/bills/{rp['id']}/sign", json={**STROKES, "text_hash": rp["text_hash"]}))
    ok(w.post(f"/api/bills/{rp['id']}/sign", json={**STROKES, "text_hash": rp["text_hash"]}))
    assert db.scalar(select(Reminder).where(Reminder.law_id == law_id)) is None
    assert f"pact-law-{law_id}@" not in h.get("/calendar/tok.ics").text


def test_push_subscribe_and_gone_subscription(clients, monkeypatch):
    h, _, db = clients
    sub = {"endpoint": "https://push.example/abc", "keys": {"p256dh": "k", "auth": "a"}}
    ok(h.post("/api/push/subscribe", json=sub))
    ok(h.post("/api/push/subscribe", json=sub))  # повтор не дублирует
    ok(h.post("/api/push/subscribe", json={**sub, "endpoint": "http://insecure"}), 422)
    assert len(db.scalars(select(PushSubscription).where(PushSubscription.endpoint == sub["endpoint"])).all()) == 1

    class Gone:
        status_code = 410

    def fake_webpush(*a, **k):
        raise push.WebPushException("gone", response=Gone())

    monkeypatch.setattr(push, "VAPID_PRIVATE_KEY", "x")
    monkeypatch.setattr(push, "webpush", fake_webpush)
    push.send_now(db, ["husband"], {"title": "t"})
    assert db.scalar(select(PushSubscription).where(PushSubscription.endpoint == sub["endpoint"])) is None
