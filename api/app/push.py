"""Web Push (VAPID). События из запросов уходят фоновой задачей после ответа, напоминания — из воркера."""

import json
import logging
import os

from fastapi import BackgroundTasks
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Session as DbSession
from .models import PushSubscription, User

log = logging.getLogger("pact.push")

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT") or "mailto:pact@example.com"


def send_now(db: Session, roles: list[str], payload: dict) -> None:
    if not VAPID_PRIVATE_KEY:
        return
    subs = db.scalars(select(PushSubscription).join(User, User.id == PushSubscription.user_id)
                      .where(User.role.in_(roles))).all()
    for s in subs:
        try:
            webpush({"endpoint": s.endpoint, "keys": s.keys}, json.dumps(payload, ensure_ascii=False),
                    vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": VAPID_SUBJECT},
                    ttl=24 * 3600, timeout=10)
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                db.delete(s)  # подписка отозвана браузером
            else:
                log.warning("push failed: %s", e)
    db.commit()


def _send_bg(roles: list[str], payload: dict) -> None:
    with DbSession() as db:
        send_now(db, roles, payload)


def notify(bg: BackgroundTasks, roles: list[str], title: str, body: str = "", url: str = "/") -> None:
    bg.add_task(_send_bg, roles, {"title": title, "body": body, "url": url})
