import os
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .db import get_db
from .models import User

COOKIE = "pact_session"
MAX_AGE = 365 * 24 * 3600

ph = PasswordHasher()
_DUMMY = ph.hash("dummy")  # чтобы время ответа не выдавало, есть ли такой логин
_signer = URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt="session")
_secure = os.environ.get("COOKIE_SECURE", "true").lower() != "false"


def check_password(user: User | None, password: str) -> bool:
    try:
        return ph.verify(user.password_hash if user else _DUMMY, password) and user is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


# ponytail: счётчик в памяти одного процесса, сбрасывается при рестарте; хватает на два аккаунта
_fails: dict[str, list[float]] = {}
LIMIT, WINDOW = 5, 15 * 60


def check_rate(ip: str) -> None:
    recent = [t for t in _fails.get(ip, []) if t > time.time() - WINDOW]
    _fails[ip] = recent
    if len(recent) >= LIMIT:
        raise HTTPException(429, "Слишком много попыток, подождите 15 минут")


def note_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def set_session(response: Response, user_id: int) -> None:
    response.set_cookie(COOKIE, _signer.dumps(user_id), max_age=MAX_AGE,
                        httponly=True, secure=_secure, samesite="lax")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE, httponly=True, secure=_secure, samesite="lax")


def current_user(pact_session: str | None = Cookie(None), db=Depends(get_db)) -> User:
    if not pact_session:
        raise HTTPException(401, "Нужен вход")
    try:
        user_id = _signer.loads(pact_session, max_age=MAX_AGE)
    except BadSignature:
        raise HTTPException(401, "Нужен вход")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "Нужен вход")
    return user


def require(role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(403, "Недостаточно прав")
        return user
    return dep
