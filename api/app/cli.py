"""python -m app.cli create-users | verify | last-hash | reembed | vapid-keys"""

import json
import os
import sys

from sqlalchemy import delete, select, update

from . import journal, pipeline
from .auth import ph
from .db import Session
from .models import Correction, User, VersionEmbedding


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


def reembed() -> None:
    """После смены EMBED_MODEL: пересчитать все эмбеддинги."""
    with Session() as db:
        db.execute(delete(VersionEmbedding))
        db.execute(update(Correction).values(embedding=None))
        pipeline.ensure_embeddings(db)
        db.commit()
    print("готово")


def vapid_keys() -> None:
    """Строки для .env: ключи VAPID для Web Push (P-256, base64url)."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    key = ec.generate_private_key(ec.SECP256R1())
    print("VAPID_PRIVATE_KEY=" + b64(key.private_numbers().private_value.to_bytes(32, "big")))
    print("VAPID_PUBLIC_KEY=" + b64(key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))


COMMANDS = {"create-users": create_users, "verify": verify, "last-hash": last_hash, "reembed": reembed,
            "vapid-keys": vapid_keys}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()
