"""Воркер: раз в минуту рассылает наступившие напоминания. python -m app.worker"""

import logging
import time
from datetime import UTC, datetime

from . import push, reminders
from .db import Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("pact.worker")


def main() -> None:
    # ponytail: простой цикл вместо APScheduler — задача одна и раз в минуту
    log.info("worker started")
    while True:
        try:
            with Session() as db:
                n = reminders.tick(db, datetime.now(UTC), lambda roles, p: push.send_now(db, roles, p))
                if n:
                    log.info("reminders sent: %d", n)
        except Exception:
            log.exception("tick failed")
        time.sleep(60 - time.time() % 60)


if __name__ == "__main__":
    main()
