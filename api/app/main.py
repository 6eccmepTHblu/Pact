import hmac
import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, bills, journal, pakt, push, reminders
from .db import get_db
from .models import Journal, Law, PushSubscription, Reminder, User

app = FastAPI(title="Пакт", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
api = APIRouter(prefix="/api")


CALENDAR_TOKEN = os.environ.get("CALENDAR_TOKEN", "")


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "role": u.role, "vapid_key": push.VAPID_PUBLIC_KEY or None,
            "calendar": f"/calendar/{CALENDAR_TOKEN}.ics" if CALENDAR_TOKEN else None}


class LoginIn(BaseModel):
    login: str
    password: str


@api.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}


@api.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db=Depends(get_db)):
    ip = request.client.host
    auth.check_rate(ip)
    user = db.scalar(select(User).where(User.login == body.login))
    if not auth.check_password(user, body.password):
        auth.note_fail(ip)
        raise HTTPException(401, "Неверный логин или пароль")
    journal.append(db, "login", actor_id=user.id, entity=f"user:{user.id}")
    db.commit()
    auth.set_session(response, user.id)
    return user_out(user)


@api.post("/auth/logout")
def logout(response: Response, user: User = Depends(auth.current_user), db=Depends(get_db)):
    journal.append(db, "logout", actor_id=user.id, entity=f"user:{user.id}")
    db.commit()
    auth.clear_session(response)
    return {"ok": True}


@api.get("/me")
def me(user: User = Depends(auth.current_user)):
    return user_out(user)


@api.get("/journal/verify")
def journal_verify(_: User = Depends(auth.require("husband")), db=Depends(get_db)):
    return journal.verify(db)


@api.get("/pakt")
def pakt_tree(_: User = Depends(auth.current_user), db=Depends(get_db)):
    return pakt.tree(db)


@api.get("/laws/{law_id}")
def get_law(law_id: int, _: User = Depends(auth.current_user), db=Depends(get_db)):
    law = db.get(Law, law_id)
    if not law:
        raise HTTPException(404, "Закон не найден")
    detail = pakt.law_detail(db, law)
    detail["done"] = [j.ts for j in db.scalars(
        select(Journal).where(Journal.action == "law_done", Journal.entity == f"law:{law.id}")
        .order_by(Journal.seq.desc()).limit(30))]
    detail["has_reminder"] = db.scalar(select(Reminder.id).where(Reminder.law_id == law.id)) is not None
    return detail


def _reminder(db, law_id: int) -> Reminder:
    r = db.scalar(select(Reminder).where(Reminder.law_id == law_id).with_for_update())
    if not r:
        raise HTTPException(409, "У закона нет расписания")
    return r


@api.post("/laws/{law_id}/done")
def law_done(law_id: int, user: User = Depends(auth.require("husband")), db=Depends(get_db)):
    law = db.get(Law, law_id)
    if not law or law.status != "active":
        raise HTTPException(404, "Закон не найден")
    r = db.scalar(select(Reminder).where(Reminder.law_id == law_id))
    if r:
        r.snoozed_until = None
    journal.append(db, "law_done", user.id, f"law:{law_id}")
    db.commit()
    return {"ok": True}


@api.post("/laws/{law_id}/snooze")
def law_snooze(law_id: int, _: User = Depends(auth.require("husband")), db=Depends(get_db)):
    r = _reminder(db, law_id)
    r.snoozed_until = datetime.now(UTC) + reminders.SNOOZE
    db.commit()
    return {"ok": True, "until": r.snoozed_until}


class SubscriptionIn(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=2000)
    keys: dict[str, str]


@api.post("/push/subscribe")
def push_subscribe(body: SubscriptionIn, user: User = Depends(auth.current_user), db=Depends(get_db)):
    s = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if s:
        s.user_id, s.keys = user.id, body.keys  # тот же браузер мог сменить учётную запись
    else:
        db.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, keys=body.keys))
    db.commit()
    return {"ok": True}


app.include_router(api)
app.include_router(bills.router)


@app.get("/calendar/{token}.ics")
def calendar(token: str, db=Depends(get_db)):
    if not CALENDAR_TOKEN or not hmac.compare_digest(token, CALENDAR_TOKEN):
        raise HTTPException(404)
    return PlainTextResponse(reminders.ics(db), media_type="text/calendar; charset=utf-8")


class SPA(StaticFiles):
    """Сборка SvelteKit: неизвестный путь отдаёт index.html, клиентский роутер разберётся."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code != 404 or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


WEB_DIR = os.environ.get("WEB_DIR", "/app/web")
if os.path.isdir(WEB_DIR):
    app.mount("/", SPA(directory=WEB_DIR, html=True))
