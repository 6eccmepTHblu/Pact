"""LLM-конвейер: разбор → место → официальная редакция → проверка смысла, few-shot на правках супруга."""

import json

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import llm, pakt
from .models import Article, Bill, Correction, Law, LawVersion, Section, VersionEmbedding


class ScheduleOut(BaseModel):
    rrule: str
    time: str


class ParseOut(BaseModel):
    title: str
    tags: list[str]
    action: str
    object: str
    schedule: ScheduleOut | None


class PlaceOut(BaseModel):
    section: str
    article: str
    is_new_section: bool
    is_new_article: bool


class OfficialOut(BaseModel):
    official_text: str


class CheckOut(BaseModel):
    meaning_lost: bool
    comment: str


class Finding(BaseModel):
    number: str
    comment: str


class ReviewOut(BaseModel):
    duplicates: list[Finding]
    contradictions: list[Finding]
    refs: list[str]


PARSE_SYS = """Ты размечаешь пожелание супруги для семейного свода законов «Пакт».
Верни:
- title — короткое название закона с заглавной буквы, в инфинитиве, без точки. Пример: «Следить за свежестью цветов в Вечной вазе».
- tags — 2–4 тега с заглавной буквы: тема; периодичность (Ежедневно, Еженедельно, Ежемесячно, Разово); тип (Действие, Запрет, Право).
- action — что сделать, глагол в инфинитиве.
- object — предмет закона; имена собственные сохраняй как в тексте.
- schedule — null, если периодичности нет. Иначе rrule по RFC 5545 (FREQ=DAILY|WEEKLY|MONTHLY, при необходимости ;BYDAY=MO,TU,… или ;BYMONTHDAY=N) и time в формате ЧЧ:ММ. Если время не названо, выбери разумное по смыслу.
Если дан действующий закон и правка, верни разметку закона после правки."""

PLACE_SYS = """Ты выбираешь место нового закона в «Пакте»: Раздел → Статья.
Раздел — широкая тема (Цветы, Быт, Деньги). Статья — конкретный предмет внутри темы (Вечная ваза).
Если закон подходит по смыслу к существующей статье или разделу из списка, выбирай их и копируй названия дословно.
Новый раздел — только если ни один существующий не подходит. Не создавай синонимов существующих разделов.
is_new_section и is_new_article — true, если такого раздела или статьи в списке нет."""

OFFICIAL_SYS = """Перепиши пожелание в официальную формулировку закона «Пакта».
Стиль: юридический, безличный, настоящее время: «Супруг обязан…», «Супруг ежедневно…».
Одно-два предложения. Не теряй смысл и не добавляй обязанностей, которых нет в пожелании. Без оценок и эмоций.
Периодичность, если она есть, называй словами.
Если дан действующий закон и правка, перепиши действующий текст с учётом правки."""

CHECK_SYS = """Сравни исходное пожелание и официальную формулировку закона.
meaning_lost = true, если формулировка теряет, искажает смысл или добавляет обязанности, которых в пожелании нет.
comment — коротко, что именно не так; пустая строка, если всё в порядке."""


REVIEW_SYS = """Ты проверяешь новый закон «Пакта» по действующим похожим законам.
duplicates — законы, которые уже требуют то же самое: новый закон их повторяет.
contradictions — законы, требования которых нельзя выполнить одновременно с новым.
refs — законы, на которые новый закон опирается: уточняет или дополняет их, без них он непонятен. Дубль — не ссылка.
comment — коротко, в чём дело. Используй только номера из списка. Если ничего нет, верни пустые списки."""


def _law_text(v: LawVersion) -> str:
    return f"{v.title}. {v.official_text}"


def ensure_embeddings(db: Session) -> None:
    """Дозаполнить эмбеддинги редакций и примеров. Подписание LLM не ждёт — недостающее добирается тут."""
    versions = db.scalars(select(LawVersion).where(
        ~select(VersionEmbedding).where(VersionEmbedding.version_id == LawVersion.id).exists())).all()
    corrections = db.execute(select(Correction, Bill.original_text).join(Bill, Bill.id == Correction.bill_id)
                             .where(Correction.embedding.is_(None))).all()
    texts = [_law_text(v) for v in versions] + [t for _, t in corrections]
    for i in range(0, len(texts), 100):
        vectors = llm.embed(texts[i:i + 100])
        for j, vec in enumerate(vectors, start=i):
            if j < len(versions):
                db.add(VersionEmbedding(version_id=versions[j].id, embedding=vec))
            else:
                corrections[j - len(versions)][0].embedding = vec
    db.flush()


def _examples(db: Session, stage: str, vec, k: int = 3) -> list[tuple[str, str]]:
    rows = db.scalars(select(Correction).where(Correction.stage == stage, Correction.embedding.is_not(None))
                      .order_by(Correction.embedding.cosine_distance(vec)).limit(k))
    return [(c.input, json.dumps(c.final, ensure_ascii=False)) for c in rows]


def _candidates(db: Session, vec, k: int = 5) -> list[dict]:
    """Top-k статей по похожести их действующих законов на пожелание."""
    rows = db.execute(
        select(Section.title, Article.id, Article.title, LawVersion.title)
        .select_from(VersionEmbedding)
        .join(LawVersion, LawVersion.id == VersionEmbedding.version_id)
        .join(Law, Law.current_version_id == LawVersion.id)
        .join(Article, Article.id == Law.article_id)
        .join(Section, Section.id == Article.section_id)
        .order_by(VersionEmbedding.embedding.cosine_distance(vec))
        .limit(k * 6))
    found: dict[int, dict] = {}
    for sec, art_id, art, law in rows:
        c = found.setdefault(art_id, {"section": sec, "article": art, "laws": []})
        if len(c["laws"]) < 3:
            c["laws"].append(law)
    return list(found.values())[:k]


def _similar_laws(db: Session, vec, exclude_id: int | None, k: int = 5) -> list[tuple[Law, LawVersion]]:
    q = (select(Law, LawVersion).join(LawVersion, LawVersion.id == Law.current_version_id)
         .join(VersionEmbedding, VersionEmbedding.version_id == LawVersion.id)
         .where(Law.status == "active"))
    if exclude_id:
        q = q.where(Law.id != exclude_id)
    return db.execute(q.order_by(VersionEmbedding.embedding.cosine_distance(vec)).limit(k)).all()


def _review(db: Session, bill: Bill, vec, title: str, official_text: str) -> tuple[list[str], list[int], dict]:
    """Дубли, противоречия и ссылки среди top-5 похожих действующих законов. Ничего не блокирует."""
    similar = _similar_laws(db, vec, bill.target_law_id)
    if not similar:
        return [], [], {}
    by_number = {pakt.law_number(db, law): (law, v) for law, v in similar}
    listing = "\n".join(f"{n} «{v.title}»: {v.official_text}" for n, (_, v) in by_number.items())
    r = llm.ask(REVIEW_SYS, [], f"Новый закон: {title}\n{official_text}\n\nДействующие законы:\n{listing}",
                ReviewOut)
    warnings = [f"{label} {f.number} «{by_number[f.number][1].title}»: {f.comment}"
                for label, found in (("Возможный дубль", r.duplicates), ("Противоречие с", r.contradictions))
                for f in found if f.number in by_number]
    refs = [by_number[n][0].id for n in dict.fromkeys(r.refs) if n in by_number]
    return warnings, refs, r.model_dump()


def _target(db: Session, bill: Bill) -> LawVersion | None:
    if not bill.target_law_id:
        return None
    return db.get(LawVersion, db.get(Law, bill.target_law_id).current_version_id)


def _hint_note(bill: Bill, hint: str | None) -> str:
    """Повторная разметка с указанием: LLM видит текущий вариант и что в нём исправить."""
    if not hint:
        return ""
    p = bill.prepared or {}
    pl, sc = p.get("placement"), p.get("schedule")
    fields = (("Название", p.get("title")), ("Текст", p.get("official_text")),
              ("Место", pl and f"раздел «{pl['section']}», статья «{pl['article']}»"),
              ("Теги", ", ".join(p.get("tags") or [])), ("Расписание", sc and f"{sc['rrule']} в {sc['time']}"))
    current = "\n".join(f"{k}: {v}" for k, v in fields if v) or "пока нет"
    return f"\n\nТекущий вариант:\n{current}\n\nУказание супруга, что исправить (выполни обязательно): {hint}"


def analyze(db: Session, bill: Bill, hint: str | None = None) -> dict:
    ensure_embeddings(db)
    vec = llm.embed([bill.original_text])[0]
    target = _target(db, bill)
    context = (f"Действующий закон: {target.title}\nТекст: {target.official_text}\n\nПравка: "
               if target else "Пожелание: ")

    note = _hint_note(bill, hint)
    inputs, outputs = {}, {}
    inputs["parse"] = context + bill.original_text + note
    parsed = llm.ask(PARSE_SYS, _examples(db, "parse", vec), inputs["parse"], ParseOut)
    outputs["parse"] = parsed.model_dump()

    if bill.kind == "new":
        cands = _candidates(db, vec)
        lines = [f"{i}. Раздел «{c['section']}» → статья «{c['article']}» (законы: {'; '.join(c['laws'])})"
                 for i, c in enumerate(cands, 1)]
        sections = db.scalars(select(Section.title).order_by(Section.number)).all()
        inputs["placement"] = (f"Закон: {parsed.title}\nДействие: {parsed.action}\nОбъект: {parsed.object}\n\n"
                               f"Похожие статьи:\n{chr(10).join(lines) or 'нет'}\n\n"
                               f"Все разделы: {', '.join(sections) or 'пока нет'}{note}")
        outputs["placement"] = llm.ask(PLACE_SYS, _examples(db, "placement", vec), inputs["placement"],
                                       PlaceOut).model_dump()

    schedule = f"\nРасписание: {parsed.schedule.rrule} в {parsed.schedule.time}" if parsed.schedule else ""
    inputs["official"] = f"{context}{bill.original_text}\n\nНазвание: {parsed.title}{schedule}{note}"
    official = llm.ask(OFFICIAL_SYS, _examples(db, "official", vec), inputs["official"], OfficialOut)
    outputs["official"] = official.model_dump()

    clarified = f"\n\nУточнение супруга: {hint}" if hint else ""  # уточнение законно меняет смысл
    check = llm.ask(CHECK_SYS, [],
                    f"Пожелание: {bill.original_text}{clarified}\n\nФормулировка: {official.official_text}", CheckOut)
    warnings = [f"Возможна потеря смысла: {check.comment}"] if check.meaning_lost else []
    review_warnings, refs, review = _review(db, bill, vec, parsed.title, official.official_text)
    return {"inputs": inputs, "outputs": outputs, "check": check.model_dump(), "review": review,
            "refs": refs, "warnings": warnings + review_warnings, "hint": hint}


def record_corrections(db: Session, bill: Bill) -> None:
    """При отправке на подпись: всё, что супруг поменял в предложении LLM, становится примером."""
    r, p = bill.llm_result, bill.prepared
    if not r:
        return
    out = r["outputs"]
    finals = {
        "parse": {**out["parse"], "title": p["title"], "tags": p["tags"], "schedule": p["schedule"]},
        "official": {"official_text": p["official_text"]},
    }
    if "placement" in out and p.get("placement"):
        sec = pakt.find_section(db, p["placement"]["section"])
        finals["placement"] = {
            **p["placement"], "is_new_section": sec is None,
            "is_new_article": not (sec and pakt.find_article(db, sec.id, p["placement"]["article"]))}
    for stage, final in finals.items():
        if final == out[stage]:
            continue
        c = db.scalar(select(Correction).where(Correction.bill_id == bill.id, Correction.stage == stage))
        if c:
            c.input, c.llm_output, c.final = r["inputs"][stage], out[stage], final
        else:
            db.add(Correction(bill_id=bill.id, stage=stage, input=r["inputs"][stage],
                              llm_output=out[stage], final=final))
