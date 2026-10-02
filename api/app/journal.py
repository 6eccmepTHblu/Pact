"""Журнал только для добавления, с хеш-цепочкой.

hash = SHA-256(prev_hash + канонический JSON записи без hash).
Хешируется вся запись, а не только payload: подмена действия, автора
или времени тоже видна.
"""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Journal

GENESIS = "0" * 64
_LOCK = 0x9AC7  # ключ advisory lock: записи идут строго по одной


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_hash(r: Journal) -> str:
    body = canonical({
        "seq": r.seq,
        "ts": r.ts.astimezone(UTC).isoformat(),
        "actor_id": r.actor_id,
        "action": r.action,
        "entity": r.entity,
        "payload": r.payload,
    })
    return hashlib.sha256((r.prev_hash + body).encode()).hexdigest()


def append(db: Session, action: str, actor_id: int | None = None,
           entity: str | None = None, payload: dict | None = None) -> Journal:
    """Добавить событие в транзакции вызывающего; commit делает он."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK})
    last = db.scalar(select(Journal).order_by(Journal.seq.desc()).limit(1))
    rec = Journal(
        seq=last.seq + 1 if last else 1,
        ts=datetime.now(UTC),
        actor_id=actor_id,
        action=action,
        entity=entity,
        payload=payload or {},
        prev_hash=last.hash if last else GENESIS,
    )
    rec.hash = compute_hash(rec)
    db.add(rec)
    db.flush()
    return rec


def verify(db: Session) -> dict:
    """Пересчитать цепочку и назвать первую несовпавшую запись."""
    prev, count = GENESIS, 0
    for r in db.scalars(select(Journal).order_by(Journal.seq).execution_options(yield_per=500)):
        count += 1
        if r.seq != count:
            return {"ok": False, "count": count, "bad_seq": r.seq, "reason": "пропуск номера"}
        if r.prev_hash != prev:
            return {"ok": False, "count": count, "bad_seq": r.seq, "reason": "разрыв цепочки"}
        if compute_hash(r) != r.hash:
            return {"ok": False, "count": count, "bad_seq": r.seq, "reason": "хеш не совпадает"}
        prev = r.hash
    return {"ok": True, "count": count, "last_hash": prev}
