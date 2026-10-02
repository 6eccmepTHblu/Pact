"""Напоминания по расписанию закона (RRULE + время по Москве) и ICS-фид."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import pakt
from .models import Law, LawVersion, Reminder

TZ = ZoneInfo("Europe/Moscow")
SNOOZE = timedelta(hours=1)


def next_fire(schedule: dict, start: datetime, after: datetime) -> datetime | None:
    """Следующее срабатывание после after. start — от него считаются «каждую неделю» и «каждый месяц»."""
    h, m = map(int, schedule["time"].split(":"))
    dtstart = start.astimezone(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    return rrulestr(schedule["rrule"], dtstart=dtstart).after(after)


def sync(db: Session, law: Law, now: datetime) -> None:
    """После вступления в силу, правки или упразднения: привести очередь в соответствие закону."""
    r = db.scalar(select(Reminder).where(Reminder.law_id == law.id))
    v = db.get(LawVersion, law.current_version_id)
    nxt = next_fire(v.schedule, v.signed_at, now) if law.status == "active" and v.schedule else None
    if nxt is None:
        if r:
            db.delete(r)
    elif r:
        r.next_fire_at, r.snoozed_until = nxt, None
    else:
        db.add(Reminder(law_id=law.id, next_fire_at=nxt))


def tick(db: Session, now: datetime, send) -> int:
    """Разослать наступившие напоминания. send(roles, payload). Возвращает число отправленных."""
    due = db.scalars(select(Reminder).where(
        func.coalesce(Reminder.snoozed_until, Reminder.next_fire_at) <= now)).all()
    for r in due:
        law = db.get(Law, r.law_id)
        v = db.get(LawVersion, law.current_version_id)
        send(["husband"], {
            "title": f"{pakt.law_number(db, law)} {v.title}", "body": v.official_text,
            "url": f"/laws/{law.id}", "law_id": law.id, "tag": f"law-{law.id}",
            "actions": [{"action": "done", "title": "Выполнено"}, {"action": "snooze", "title": "Отложить на час"}]})
        r.snoozed_until = None
        if r.next_fire_at <= now:
            nxt = next_fire(v.schedule, v.signed_at, now)
            if nxt is None:
                db.delete(r)
            else:
                r.next_fire_at = nxt
    db.commit()
    return len(due)


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: строки не длиннее 75 октетов, перенос — CRLF и пробел. Не режем символ UTF-8 пополам."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ""
        cur += ch
    return "\r\n ".join(out + [cur])


def ics(db: Session) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pact//RU", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Пакт", "X-WR-TIMEZONE:Europe/Moscow",
             "BEGIN:VTIMEZONE", "TZID:Europe/Moscow", "BEGIN:STANDARD", "DTSTART:19700101T000000",
             "TZOFFSETFROM:+0300", "TZOFFSETTO:+0300", "TZNAME:MSK", "END:STANDARD", "END:VTIMEZONE"]
    rows = db.execute(select(Law, LawVersion).join(LawVersion, LawVersion.id == Law.current_version_id)
                      .where(Law.status == "active", LawVersion.schedule.is_not(None)).order_by(Law.id))
    for law, v in rows:
        h, m = map(int, v.schedule["time"].split(":"))
        day = v.signed_at.astimezone(TZ)
        lines += ["BEGIN:VEVENT", f"UID:pact-law-{law.id}@pact", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID=Europe/Moscow:{day:%Y%m%d}T{h:02}{m:02}00", "DURATION:PT15M",
                  f"RRULE:{v.schedule['rrule']}",
                  f"SUMMARY:{_esc(pakt.law_number(db, law) + ' ' + v.title)}",
                  f"DESCRIPTION:{_esc(v.official_text)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
