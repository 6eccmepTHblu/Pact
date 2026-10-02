"""Структура Пакта: номера, вступление в силу, подписываемый текст, SVG подписи."""

import hashlib
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .journal import canonical
from .models import Article, Bill, Law, LawRef, LawVersion, Section, Signature, User

_STRUCTURE_LOCK = 0x9AC8  # номера выдаются строго по одному


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _next(db: Session, col, *where) -> int:
    return (db.scalar(select(func.max(col)).where(*where)) or 0) + 1


def find_section(db: Session, title: str) -> Section | None:
    return db.scalar(select(Section).where(func.lower(Section.title) == title.lower()))


def find_article(db: Session, section_id: int, title: str) -> Article | None:
    return db.scalar(select(Article).where(Article.section_id == section_id,
                                           func.lower(Article.title) == title.lower()))


def law_number(db: Session, law: Law) -> str:
    art = db.get(Article, law.article_id)
    sec = db.get(Section, art.section_id)
    return f"{sec.number}.{art.number}.{law.number}"


def preview_number(db: Session, bill: Bill) -> str | None:
    """Номер для черновика. Окончательный выдаётся при подписании."""
    if bill.target_law_id:
        return law_number(db, db.get(Law, bill.target_law_id))
    if bill.status == "enacted":
        law_id = db.scalar(select(LawVersion.law_id).where(LawVersion.bill_id == bill.id))
        return law_number(db, db.get(Law, law_id))
    placement = (bill.prepared or {}).get("placement")
    if not placement:
        return None
    sec = find_section(db, placement["section"])
    if not sec:
        return f"{_next(db, Section.number)}.1.1"
    art = find_article(db, sec.id, placement["article"])
    if not art:
        return f"{sec.number}.{_next(db, Article.number, Article.section_id == sec.id)}.1"
    return f"{sec.number}.{art.number}.{_next(db, Law.number, Law.article_id == art.id)}"


def bill_content(db: Session, bill: Bill) -> dict:
    """То, что подписывается. Его хеш закрепляет подпись за конкретной редакцией."""
    if bill.kind == "repeal":
        return {"kind": "repeal", "law_id": bill.target_law_id,
                "number": law_number(db, db.get(Law, bill.target_law_id)),
                "reason": bill.original_text}
    p = bill.prepared or {}
    content = {"kind": bill.kind, "law_id": bill.target_law_id, "original_text": bill.original_text,
               **{k: p.get(k) for k in ("title", "official_text", "tags", "schedule", "placement")}}
    if p.get("refs"):  # только непустые: хеш подписанных до этапа 4 законов не меняется
        content["refs"] = sorted(p["refs"])
    return content


def text_hash(db: Session, bill: Bill) -> str:
    return sha256(canonical(bill_content(db, bill)))


def _f(v: float) -> str:
    return f"{round(v, 1):g}"


def render_svg(width: float, height: float, strokes: list) -> str:
    """SVG строит сервер из чисел: в него не попадёт ничего, кроме путей."""
    paths = []
    for pts in strokes:
        (x0, y0), rest = pts[0], pts[1:]
        d = f"M{_f(x0)} {_f(y0)}"
        if not rest:
            d += "l0.1 0"
        # сглаживание: квадратичные кривые через середины отрезков
        for (x1, y1), (x2, y2) in zip(rest, rest[1:]):
            d += f"Q{_f(x1)} {_f(y1)} {_f((x1 + x2) / 2)} {_f((y1 + y2) / 2)}"
        if rest:
            d += f"L{_f(rest[-1][0])} {_f(rest[-1][1])}"
        paths.append(f'<path d="{d}"/>')
    # viewBox по габаритам штрихов, а не всего холста: подпись не тонет в пустом поле
    xs = [x for pts in strokes for x, _ in pts]
    ys = [y for pts in strokes for _, y in pts]
    pad = 4
    x0, y0 = max(min(xs) - pad, 0), max(min(ys) - pad, 0)
    w, h = min(max(xs) + pad, width) - x0, min(max(ys) + pad, height) - y0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_f(x0)} {_f(y0)} {_f(w)} {_f(h)}" '
            'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
            f'stroke-linejoin="round">{"".join(paths)}</svg>')


def enact(db: Session, bill: Bill, now: datetime) -> tuple[Law, str, dict]:
    """Ввести законопроект в силу. Вызывается под блокировкой законопроекта."""
    if bill.kind == "new":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _STRUCTURE_LOCK})
        placement = bill.prepared["placement"]
        sec = find_section(db, placement["section"])
        if not sec:
            sec = Section(number=_next(db, Section.number), title=placement["section"])
            db.add(sec)
            db.flush()
        art = find_article(db, sec.id, placement["article"])
        if not art:
            art = Article(section_id=sec.id, number=_next(db, Article.number, Article.section_id == sec.id),
                          title=placement["article"])
            db.add(art)
            db.flush()
        law = Law(article_id=art.id, number=_next(db, Law.number, Law.article_id == art.id),
                  status="active", enacted_at=now)
        db.add(law)
        db.flush()
        version_no, action = 1, "law_enacted"
    else:
        law = db.scalar(select(Law).where(Law.id == bill.target_law_id).with_for_update())
        if law.status != "active":
            raise HTTPException(409, "Закон уже утратил силу")
        if bill.kind == "repeal":
            law.status, law.repealed_at = "repealed", now
            return law, "law_repealed", {"number": law_number(db, law)}
        version_no, action = _next(db, LawVersion.version_no, LawVersion.law_id == law.id), "law_amended"

    p = bill.prepared
    version = LawVersion(law_id=law.id, version_no=version_no, title=p["title"],
                         official_text=p["official_text"], original_text=bill.original_text,
                         tags=p.get("tags") or [], schedule=p.get("schedule"),
                         bill_id=bill.id, signed_at=now)
    db.add(version)
    db.flush()
    law.current_version_id = version.id
    set_refs(db, law, p.get("refs") or [])
    return law, action, {"number": law_number(db, law), "version": version_no}


def set_refs(db: Session, law: Law, ids: list[int]) -> None:
    db.execute(delete(LawRef).where(LawRef.from_law_id == law.id))
    for to in db.scalars(select(Law.id).where(Law.id.in_(ids), Law.status == "active", Law.id != law.id)):
        db.add(LawRef(from_law_id=law.id, to_law_id=to))


def law_brief(db: Session, law: Law) -> dict:
    return {"id": law.id, "number": law_number(db, law), "status": law.status,
            "title": db.get(LawVersion, law.current_version_id).title}


def refs_of(db: Session, law_id: int) -> list[dict]:
    """На какие законы опирается."""
    return [law_brief(db, l) for l in db.scalars(
        select(Law).join(LawRef, LawRef.to_law_id == Law.id).where(LawRef.from_law_id == law_id))]


def referenced_by(db: Session, law_id: int) -> list[dict]:
    """Какие действующие законы опираются на этот: их надо проверить при упразднении."""
    return [law_brief(db, l) for l in db.scalars(
        select(Law).join(LawRef, LawRef.from_law_id == Law.id)
        .where(LawRef.to_law_id == law_id, Law.status == "active"))]


def tree(db: Session) -> list[dict]:
    sections = {s.id: {"id": s.id, "number": s.number, "title": s.title, "articles": []}
                for s in db.scalars(select(Section).order_by(Section.number))}
    articles = {}
    for a in db.scalars(select(Article).order_by(Article.number)):
        articles[a.id] = {"id": a.id, "number": a.number, "title": a.title, "laws": []}
        sections[a.section_id]["articles"].append(articles[a.id])
    rows = db.execute(select(Law, LawVersion.title)
                      .join(LawVersion, LawVersion.id == Law.current_version_id).order_by(Law.number))
    for law, title in rows:
        articles[law.article_id]["laws"].append({
            "id": law.id, "number": law.number, "title": title,
            "status": law.status, "repealed_at": law.repealed_at})
    return list(sections.values())


def signatures_of(db: Session, bill: Bill) -> list[dict]:
    """Последняя подпись каждой стороны под итоговым текстом; подписи до возврата не показываются."""
    h = text_hash(db, bill)
    rows = db.execute(select(Signature, User).join(User, User.id == Signature.user_id)
                      .where(Signature.bill_id == bill.id, Signature.text_hash == h)
                      .order_by(Signature.signed_at))
    last = {u.id: {"name": u.name, "role": u.role, "svg": s.svg, "signed_at": s.signed_at} for s, u in rows}
    return sorted(last.values(), key=lambda s: s["signed_at"])


def law_detail(db: Session, law: Law) -> dict:
    art = db.get(Article, law.article_id)
    sec = db.get(Section, art.section_id)
    versions = []
    for v in db.scalars(select(LawVersion).where(LawVersion.law_id == law.id).order_by(LawVersion.version_no.desc())):
        versions.append({
            "version_no": v.version_no, "title": v.title, "official_text": v.official_text,
            "original_text": v.original_text, "tags": v.tags, "schedule": v.schedule,
            "signed_at": v.signed_at, "signatures": signatures_of(db, db.get(Bill, v.bill_id))})
    repeal = None
    if law.status == "repealed":
        bill = db.scalar(select(Bill).where(Bill.kind == "repeal", Bill.target_law_id == law.id,
                                            Bill.status == "enacted"))
        repeal = {"reason": bill.original_text, "signatures": signatures_of(db, bill)}
    return {
        "id": law.id, "number": f"{sec.number}.{art.number}.{law.number}", "status": law.status,
        "enacted_at": law.enacted_at, "repealed_at": law.repealed_at,
        "section": {"number": sec.number, "title": sec.title},
        "article": {"number": art.number, "title": art.title},
        "versions": versions, "repeal": repeal,
        "refs": refs_of(db, law.id), "referenced_by": referenced_by(db, law.id),
    }
