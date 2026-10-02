import os

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, journal
from .db import get_db
from .models import User

app = FastAPI(title="Пакт", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
api = APIRouter(prefix="/api")


def user_out(u: User) -> dict:
    return {"id": u.id, "name": u.name, "role": u.role}


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


app.include_router(api)


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
