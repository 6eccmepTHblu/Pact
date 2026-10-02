"""python -m app.cli create-users | verify | last-hash"""

import json
import os
import sys

from sqlalchemy import select

from . import journal
from .auth import ph
from .db import Session
from .models import User


def create_users() -> None:
    with Session() as db:
        for role in ("husband", "wife"):
            p = role.upper()
            if db.scalar(select(User).where(User.role == role)):
                print(f"{role}: уже есть, пропускаю")
                continue
            login, password = os.environ.get(f"{p}_LOGIN"), os.environ.get(f"{p}_PASSWORD")
            if not login or not password:
                sys.exit(f"{p}_LOGIN и {p}_PASSWORD не заданы")
            user = User(login=login, name=os.environ.get(f"{p}_NAME") or login,
                        role=role, password_hash=ph.hash(password))
            db.add(user)
            db.flush()
            journal.append(db, "user_created", entity=f"user:{user.id}",
                           payload={"role": role, "login": login})
            print(f"{role}: создан {login}")
        db.commit()


def verify() -> None:
    with Session() as db:
        result = journal.verify(db)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


def last_hash() -> None:
    with Session() as db:
        result = journal.verify(db)
    if not result["ok"]:
        sys.exit(json.dumps(result, ensure_ascii=False))
    print(result["last_hash"])


COMMANDS = {"create-users": create_users, "verify": verify, "last-hash": last_hash}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()
