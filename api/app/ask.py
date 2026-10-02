"""Спросить Пакт: ответ только по действующим законам, со ссылками на номера. В журнал не пишется."""

import re

import openai
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import llm, pakt, pipeline
from .auth import current_user
from .db import get_db
from .models import Law, LawVersion, User, VersionEmbedding

router = APIRouter(prefix="/api")

NOT_FOUND = "В Пакте об этом ничего не сказано."
CITE = re.compile(r"\[(\d+\.\d+\.\d+)\]")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
SPACES = re.compile(r"[ \t]{2,}")

ASK_SYS = """Ты отвечаешь на вопрос по семейному своду законов «Пакт» строго по приведённым действующим законам.
Каждое утверждение сопровождай номером закона в квадратных скобках, например [4.1.1].
Не добавляй ничего, чего нет в текстах законов, и не додумывай. Если законы не отвечают на вопрос, верни found=false.
Отвечай кратко, по-русски, от третьего лица («Супруг обязан…»)."""


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class AskOut(BaseModel):
    found: bool
    answer: str


@router.post("/ask")
def ask(body: AskIn, _: User = Depends(current_user), db=Depends(get_db)):
    try:
        pipeline.ensure_embeddings(db)
        db.commit()
        vec = llm.embed([body.question])[0]
        rows = db.execute(
            select(Law, LawVersion).join(LawVersion, LawVersion.id == Law.current_version_id)
            .join(VersionEmbedding, VersionEmbedding.version_id == LawVersion.id)
            .where(Law.status == "active")  # упразднённые в ответ не попадают
            .order_by(VersionEmbedding.embedding.cosine_distance(vec)).limit(8)).all()
        if not rows:
            return {"answer": NOT_FOUND, "laws": []}
        laws = {pakt.law_number(db, law): (law, v) for law, v in rows}
        context = "\n".join(f"[{n}] {v.title}: {v.official_text}" for n, (_, v) in laws.items())
        r = llm.ask(ASK_SYS, [], f"Законы:\n{context}\n\nВопрос: {body.question}", AskOut)
    except openai.OpenAIError as e:
        raise HTTPException(502, llm.human_error(e))

    # Ссылки только на законы из контекста; выдуманные номера вычищаются. Без единой ссылки — не ответ.
    answer = CITE.sub(lambda m: m.group(0) if m.group(1) in laws else "", r.answer)
    answer = SPACE_BEFORE_PUNCT.sub(lambda m: m.group(1), SPACES.sub(" ", answer)).strip()
    cited = list(dict.fromkeys(CITE.findall(answer)))
    if not r.found or not cited:
        return {"answer": NOT_FOUND, "laws": []}
    return {"answer": answer,
            "laws": [{"id": laws[n][0].id, "number": n, "title": laws[n][1].title} for n in cited]}
