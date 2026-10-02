"""Полный цикл законопроекта через API, в одной транзакции с откатом."""

from app import journal

STROKES = {"width": 300, "height": 120, "strokes": [[[10, 60], [40, 20], [80, 90], [120, 40]], [[150, 60]]]}


def ok(r, code=200):
    assert r.status_code == code, r.text
    return r.json()


def new_bill(h, section, article, title):
    return ok(h.post("/api/bills", json={
        "kind": "new", "original_text": f"хочу: {title}",
        "prepared": {"title": title, "official_text": f"Супруг обязан: {title}.", "tags": ["Тест"],
                     "schedule": {"rrule": "FREQ=DAILY", "time": "19:00"},
                     "placement": {"section": section, "article": article}}}))


def sign(c, bill, **extra):
    return c.post(f"/api/bills/{bill['id']}/sign", json={**STROKES, "text_hash": bill["text_hash"], **extra})


def test_full_cycle(clients):
    h, w, db = clients

    # Новый закон: черновик не виден супруге, подпись привязана к тексту
    b = new_bill(h, "Цветы-тест", "Вечная ваза", "Следить за цветами")
    assert b["status"] == "draft" and b["number"].endswith(".1.1")
    ok(w.get(f"/api/bills/{b['id']}"), 404)
    assert ok(w.post("/api/bills", json={"kind": "new", "original_text": "x"}))["status"] == "request"
    ok(sign(w, b), 404)  # черновик супруге не виден
    b = ok(h.post(f"/api/bills/{b['id']}/submit"))
    assert b["status"] == "pending"
    ok(sign(w, b, text_hash="0" * 64), 409)
    ok(sign(h, b), 409)  # новый закон подписывает только супруга
    b = ok(sign(w, b))
    assert b["status"] == "enacted" and b["law_id"]
    law = ok(h.get(f"/api/laws/{b['law_id']}"))
    sec_no = law["number"].split(".")[0]
    assert law["number"] == b["number"] == f"{sec_no}.1.1"
    sig = law["versions"][0]["signatures"][0]
    assert sig["role"] == "wife" and sig["svg"].startswith("<svg") and "<script" not in sig["svg"]

    # Два параллельных проекта в тот же раздел (другой регистр): без дубля раздела, номера по порядку
    b2 = ok(h.post(f"/api/bills/{new_bill(h, 'цветы-тест', 'вечная ваза', 'Второй')['id']}/submit"))
    b3 = ok(h.post(f"/api/bills/{new_bill(h, 'Цветы-тест', 'Вечная ваза', 'Третий')['id']}/submit"))
    assert b2["number"] == b3["number"] == f"{sec_no}.1.2"  # предварительный номер одинаковый
    n3 = ok(h.get(f"/api/laws/{ok(sign(w, b3))['law_id']}"))["number"]
    n2 = ok(h.get(f"/api/laws/{ok(sign(w, b2))['law_id']}"))["number"]
    assert (n3, n2) == (f"{sec_no}.1.2", f"{sec_no}.1.3")

    # Правка: возврат с комментарием, повторная отправка, новая редакция с тем же номером
    a = ok(h.post("/api/bills", json={"kind": "amend", "target_law_id": law["id"], "original_text": "чаще"}))
    assert a["prepared"]["title"] == "Следить за цветами"
    prepared = {**a["prepared"], "official_text": "Супруг обязан менять цветы дважды в день."}
    a = ok(h.put(f"/api/bills/{a['id']}/prepared", json={"original_text": "чаще", "prepared": prepared}))
    a = ok(h.post(f"/api/bills/{a['id']}/submit"))
    a = ok(w.post(f"/api/bills/{a['id']}/return", json={"comment": "Не дважды, а утром"}))
    assert a["status"] == "returned" and a["wife_comment"] == "Не дважды, а утром"
    ok(w.get(f"/api/bills/{a['id']}"), 404)  # возвращённый снова виден только супругу
    a = ok(h.post(f"/api/bills/{a['id']}/submit"))
    ok(sign(w, a))
    law = ok(h.get(f"/api/laws/{law['id']}"))
    assert [v["version_no"] for v in law["versions"]] == [2, 1]
    assert law["number"] == f"{sec_no}.1.1"
    assert law["versions"][0]["official_text"] == "Супруг обязан менять цветы дважды в день."

    # Упразднение: первым подписывает супруг, отказ супруги, затем две подписи
    r = ok(h.post("/api/bills", json={"kind": "repeal", "target_law_id": law["id"], "original_text": "не нужен"}))
    ok(h.post(f"/api/bills/{r['id']}/submit"), 409)
    ok(sign(w, r), 404)  # черновик супруге не виден
    r = ok(sign(h, r))
    assert r["status"] == "partial"
    r = ok(w.post(f"/api/bills/{r['id']}/return", json={"comment": "подумаем"}))
    r = ok(sign(h, r))
    r = ok(sign(w, r))
    assert r["status"] == "enacted"
    law = ok(h.get(f"/api/laws/{law['id']}"))
    assert law["status"] == "repealed" and law["repealed_at"]
    assert [s["role"] for s in law["repeal"]["signatures"]] == ["husband", "wife"]  # без подписи до отказа
    ok(h.post("/api/bills", json={"kind": "amend", "target_law_id": law["id"], "original_text": "x"}), 422)

    # Упразднённый закон остаётся в дереве на своём месте
    tree = ok(w.get("/api/pakt"))
    laws = [l for s in tree if str(s["number"]) == sec_no for a in s["articles"] for l in a["laws"]]
    assert [(l["number"], l["status"]) for l in laws] == [(1, "repealed"), (2, "active"), (3, "active")]

    assert journal.verify(db)["ok"]
