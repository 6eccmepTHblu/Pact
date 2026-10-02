"""Законопроекты. Статус меняется только через действия, прямого PATCH status нет.

new/amend: draft|returned →submit→ pending →подпись супруги→ enacted
repeal:    draft|returned →подпись инициатора→ partial →подпись второй стороны→ enacted
pending|partial →return (супруга)→ returned;  draft|returned →withdraw→ withdrawn
заявка супруги: request →accept→ draft (дальше как выше) | request →reject→ rejected
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

import openai
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from sqlalchemy import select

from . import journal, pakt, pipeline, push, reminders
from .auth import current_user, require
from .db import get_db
from .models import Bill, Law, LawVersion, Signature, User

router = APIRouter(prefix="/api/bills")

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class Schedule(BaseModel):
    rrule: str = Field(pattern=r"^FREQ=(DAILY|WEEKLY|MONTHLY)(;[A-Z]+=[A-Z0-9,+-]+)*$", max_length=200)
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class Placement(BaseModel):
    section: Title
    article: Title


class Prepared(BaseModel):
    title: Title
    official_text: Text
    tags: list[Tag] = Field(default=[], max_length=20)
    schedule: Schedule | None = None
    placement: Placement | None = None
    refs: list[int] = Field(default=[], max_length=30)


class BillIn(BaseModel):
    kind: Literal["new", "amend", "repeal"]
    target_law_id: int | None = None
    original_text: Text
    prepared: Prepared | None = None


class PreparedIn(BaseModel):
    original_text: Text
    prepared: Prepared | None = None


class CommentIn(BaseModel):
    comment: Text


Point = tuple[Annotated[float, Field(ge=0, le=4000)], Annotated[float, Field(ge=0, le=4000)]]


class SignIn(BaseModel):
    width: float = Field(gt=0, le=4000)
    height: float = Field(gt=0, le=4000)
    strokes: list[Annotated[list[Point], Field(min_length=1, max_length=3000)]] = Field(min_length=1, max_length=300)
    text_hash: str


WIFE_VISIBLE = ("pending", "partial", "enacted")
HIDDEN_FROM_WIFE = ("draft", "returned", "withdrawn")  # её заявка в работе: видна, но без черновой разметки


def _load(db, bill_id: int, user: User, lock: bool = False) -> Bill:
    q = select(Bill).where(Bill.id == bill_id)
    bill = db.scalar(q.with_for_update() if lock else q)
    if not bill or (user.role == "wife" and bill.status not in WIFE_VISIBLE and bill.created_by != user.id):
        raise HTTPException(404, "Законопроект не найден")
    return bill


def _expect(bill: Bill, *statuses: str) -> None:
    if bill.status not in statuses:
        raise HTTPException(409, "Действие недоступно в текущем статусе")


def _active_law(db, law_id: int | None) -> Law:
    law = db.get(Law, law_id) if law_id else None
    if not law or law.status != "active":
        raise HTTPException(422, "Нужен действующий закон")
    return law


def _title(db, bill: Bill) -> str:
    if bill.prepared and bill.prepared.get("title"):
        return bill.prepared["title"]
    if bill.target_law_id:
        law = db.get(Law, bill.target_law_id)
        return db.get(LawVersion, law.current_version_id).title
    return bill.original_text[:80]


def _redacted(bill: Bill, user: User | None) -> bool:
    return user is not None and user.role == "wife" and bill.status in HIDDEN_FROM_WIFE


def bill_brief(db, bill: Bill, user: User | None = None) -> dict:
    hidden = _redacted(bill, user)
    return {"id": bill.id, "kind": bill.kind, "status": bill.status,
            "mine": user is not None and bill.created_by == user.id,
            "title": bill.original_text[:80] if hidden else _title(db, bill),
            "number": None if hidden and bill.kind == "new" else pakt.preview_number(db, bill),
            "updated_at": bill.updated_at}


def bill_out(db, bill: Bill, user: User | None = None) -> dict:
    out = _bill_out(db, bill, user)
    if _redacted(bill, user):
        out.update(prepared=None, refs=[], warnings=[])
    return out


def _bill_out(db, bill: Bill, user: User | None) -> dict:
    out = {**bill_brief(db, bill, user), "original_text": bill.original_text, "prepared": bill.prepared,
           "wife_comment": bill.wife_comment, "reject_reason": bill.reject_reason, "created_at": bill.created_at,
           "text_hash": pakt.text_hash(db, bill), "target": None, "law_id": bill.target_law_id,
           "signatures": pakt.signatures_of(db, bill),
           "warnings": (bill.llm_result or {}).get("warnings", []) if bill.status in ("draft", "returned") else []}
    if bill.target_law_id:
        law = db.get(Law, bill.target_law_id)
        v = db.get(LawVersion, law.current_version_id)
        out["target"] = {"id": law.id, "number": pakt.law_number(db, law), "status": law.status,
                         "title": v.title, "official_text": v.official_text,
                         "referenced_by": pakt.referenced_by(db, law.id)}
    out["refs"] = [pakt.law_brief(db, l) for l in db.scalars(
        select(Law).where(Law.id.in_((bill.prepared or {}).get("refs") or [])))]
    if bill.kind == "new" and bill.status == "enacted":
        out["law_id"] = db.scalar(select(LawVersion.law_id).where(LawVersion.bill_id == bill.id))
    return out


def to_prepared(result: dict) -> dict:
    """Предложение конвейера в формате prepared. Невалидное расписание отбрасывается с предупреждением."""
    out = result["outputs"]
    placement = out.get("placement")
    raw = {**out["parse"], "official_text": out["official"]["official_text"],
           "placement": placement and {"section": placement["section"], "article": placement["article"]},
           "refs": result.get("refs", [])}
    try:
        return Prepared.model_validate(raw).model_dump()
    except ValidationError:
        result["warnings"].append(f"Расписание не распознано: {out['parse']['schedule']}")
    try:
        return Prepared.model_validate({**raw, "schedule": None}).model_dump()
    except ValidationError:
        raise HTTPException(502, "LLM вернул разметку, которая не проходит проверку")


def _check_complete(db, bill: Bill) -> None:
    p = bill.prepared
    if not p or (bill.kind == "new" and not p.get("placement")):
        raise HTTPException(422, "Заполните формулировку и место в Пакте")
    refs = set(p.get("refs") or [])
    active = set(db.scalars(select(Law.id).where(Law.id.in_(refs), Law.status == "active")))
    if refs - active or bill.target_law_id in refs:
        raise HTTPException(422, "Ссылаться можно только на другие действующие законы")


@router.post("")
def create(body: BillIn, bg: BackgroundTasks, user: User = Depends(current_user), db=Depends(get_db)):
    request = user.role == "wife"  # супруга подаёт заявку, супруг создаёт черновик
    prepared = body.prepared.model_dump() if body.prepared and not request else None
    if body.kind == "new":
        if body.target_law_id:
            raise HTTPException(422, "У нового закона нет целевого закона")
    else:
        law = _active_law(db, body.target_law_id)
        if body.kind == "repeal":
            prepared = None
        elif prepared is None and not request:
            v = db.get(LawVersion, law.current_version_id)
            prepared = {"title": v.title, "official_text": v.official_text, "tags": v.tags,
                        "schedule": v.schedule, "placement": None,
                        "refs": [r["id"] for r in pakt.refs_of(db, law.id)]}
    if prepared and body.kind == "amend":
        prepared["placement"] = None  # правка не двигает закон: номер неизменен
    bill = Bill(kind=body.kind, target_law_id=body.target_law_id, status="request" if request else "draft",
                original_text=body.original_text, prepared=prepared, created_by=user.id)
    db.add(bill)
    db.flush()
    journal.append(db, "request_submitted" if request else "bill_created", user.id, f"bill:{bill.id}",
                   {"kind": bill.kind})
    db.commit()
    if request:
        push.notify(bg, ["husband"], "Подана заявка", bill.original_text, f"/bills/{bill.id}")
    return bill_out(db, bill, user)


@router.post("/{bill_id}/accept")
def accept(bill_id: int, user: User = Depends(require("husband")), db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "request")
    if bill.kind != "new":
        law = _active_law(db, bill.target_law_id)
        if bill.kind == "amend":  # правка начинается с действующей редакции
            v = db.get(LawVersion, law.current_version_id)
            bill.prepared = {"title": v.title, "official_text": v.official_text, "tags": v.tags,
                             "schedule": v.schedule, "placement": None,
                             "refs": [r["id"] for r in pakt.refs_of(db, law.id)]}
    bill.status = "draft"
    journal.append(db, "request_accepted", user.id, f"bill:{bill.id}")
    db.commit()
    return bill_out(db, bill, user)


@router.post("/{bill_id}/reject")
def reject(bill_id: int, body: CommentIn, bg: BackgroundTasks, user: User = Depends(require("husband")),
           db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "request")
    bill.status, bill.reject_reason = "rejected", body.comment
    journal.append(db, "request_rejected", user.id, f"bill:{bill.id}", {"reason": body.comment})
    db.commit()
    push.notify(bg, ["wife"], "Заявка отклонена", body.comment, f"/bills/{bill.id}")
    return bill_out(db, bill, user)


@router.get("")
def list_bills(status: str | None = None, user: User = Depends(current_user), db=Depends(get_db)):
    q = select(Bill).order_by(Bill.updated_at.desc())
    if user.role == "wife":
        q = q.where(Bill.status.in_(WIFE_VISIBLE) | (Bill.created_by == user.id))
    if status:
        q = q.where(Bill.status.in_(status.split(",")))
    return [bill_brief(db, b, user) for b in db.scalars(q)]


@router.get("/{bill_id}")
def get_bill(bill_id: int, user: User = Depends(current_user), db=Depends(get_db)):
    return bill_out(db, _load(db, bill_id, user), user)


@router.put("/{bill_id}/prepared")
def save_prepared(bill_id: int, body: PreparedIn, user: User = Depends(require("husband")), db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "draft", "returned")
    bill.original_text = body.original_text
    if bill.kind != "repeal" and body.prepared:
        prepared = body.prepared.model_dump()
        if bill.kind == "amend":
            prepared["placement"] = None
        bill.prepared = prepared
    db.commit()
    return bill_out(db, bill, user)


@router.post("/{bill_id}/analyze")
def analyze(bill_id: int, user: User = Depends(require("husband")), db=Depends(get_db)):
    # ponytail: синхронно в запросе (10–20 с); в фон — когда появится воркер
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "draft", "returned")
    if bill.kind == "repeal":
        raise HTTPException(409, "Упразднение не размечается")
    try:
        result = pipeline.analyze(db, bill)
    except openai.OpenAIError as e:
        raise HTTPException(502, f"LLM недоступен: {type(e).__name__}")
    # prepared собирается целиком и присваивается один раз: правки JSONB на месте SQLAlchemy не видит
    prepared = to_prepared(result)
    if bill.kind == "amend":
        prepared["placement"] = None
        # правка не теряет существующие ссылки закона, LLM лишь добавляет новые
        current = [r["id"] for r in pakt.refs_of(db, bill.target_law_id)]
        prepared["refs"] = list(dict.fromkeys(current + prepared["refs"]))
    bill.prepared, bill.llm_result = prepared, result
    db.commit()
    return bill_out(db, bill, user)


@router.post("/{bill_id}/submit")
def submit(bill_id: int, bg: BackgroundTasks, user: User = Depends(require("husband")), db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "draft", "returned")
    if bill.kind == "repeal":
        raise HTTPException(409, "Упразднение отправляется подписью инициатора")
    _check_complete(db, bill)
    pipeline.record_corrections(db, bill)
    bill.status = "pending"
    journal.append(db, "bill_submitted", user.id, f"bill:{bill.id}", {"text_hash": pakt.text_hash(db, bill)})
    db.commit()
    push.notify(bg, ["wife"], "Законопроект на подписи", _title(db, bill), f"/bills/{bill.id}")
    return bill_out(db, bill, user)


@router.post("/{bill_id}/withdraw")
def withdraw(bill_id: int, user: User = Depends(require("husband")), db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "draft", "returned")
    bill.status = "withdrawn"
    journal.append(db, "bill_withdrawn", user.id, f"bill:{bill.id}")
    db.commit()
    return bill_out(db, bill, user)


@router.post("/{bill_id}/return")
def return_bill(bill_id: int, body: CommentIn, bg: BackgroundTasks, user: User = Depends(require("wife")),
                db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    _expect(bill, "pending", "partial")
    bill.status, bill.wife_comment = "returned", body.comment
    journal.append(db, "bill_returned", user.id, f"bill:{bill.id}", {"comment": body.comment})
    db.commit()
    push.notify(bg, ["husband"], "Законопроект возвращён с правками", body.comment, f"/bills/{bill.id}")
    return bill_out(db, bill, user)


@router.post("/{bill_id}/sign")
def sign(bill_id: int, body: SignIn, bg: BackgroundTasks, user: User = Depends(current_user), db=Depends(get_db)):
    bill = _load(db, bill_id, user, lock=True)
    # Кто и когда подписывает. Упразднение по заявке супруги (этап 5) тоже начинает супруг.
    if bill.kind == "repeal":
        first = user.role == "husband" and bill.status in ("draft", "returned")
        final = user.role == "wife" and bill.status == "partial"
    else:
        first, final = False, user.role == "wife" and bill.status == "pending"
    if not (first or final):
        raise HTTPException(409, "Подпись сейчас недоступна")
    if bill.kind == "repeal":
        _active_law(db, bill.target_law_id)

    th = pakt.text_hash(db, bill)
    if body.text_hash != th:
        raise HTTPException(409, "Текст законопроекта изменился, откройте его заново")

    now = datetime.now(UTC)
    svg = pakt.render_svg(body.width, body.height, body.strokes)
    sig = Signature(bill_id=bill.id, user_id=user.id, svg=svg, svg_hash=pakt.sha256(svg), text_hash=th,
                    strokes={"width": body.width, "height": body.height, "strokes": body.strokes},
                    signed_at=now)
    db.add(sig)
    db.flush()
    journal.append(db, "bill_signed", user.id, f"bill:{bill.id}",
                   {"signature_id": sig.id, "svg_hash": sig.svg_hash, "text_hash": th})
    if final:
        law, action, payload = pakt.enact(db, bill, now)
        bill.status = "enacted"
        journal.append(db, action, user.id, f"law:{law.id}", {**payload, "bill_id": bill.id})
        reminders.sync(db, law, now)
    else:
        bill.status = "partial"
    db.commit()
    if final:
        title = {"law_enacted": "Закон вступил в силу", "law_amended": "Новая редакция вступила в силу",
                 "law_repealed": "Закон упразднён"}[action]
        push.notify(bg, ["husband", "wife"], title, f"{payload['number']} {_title(db, bill)}", f"/laws/{law.id}")
    else:
        push.notify(bg, ["wife"], "Упразднение ждёт подписи", _title(db, bill), f"/bills/{bill.id}")
    return bill_out(db, bill, user)
