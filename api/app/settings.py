"""Настройки LLM: провайдер, модели, ключ. Только супруг; ключ наружу не отдаётся."""

import openai
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, update

from . import journal, llm
from .auth import require
from .db import get_db
from .models import Correction, Setting, User, VersionEmbedding

router = APIRouter(prefix="/api/settings/llm")

Provider = Field(pattern="^(" + "|".join(llm.PROVIDERS) + ")$")


class ProbeIn(BaseModel):
    provider: str = Provider
    api_key: str | None = Field(default=None, max_length=500)
    chat_model: str | None = Field(default=None, max_length=200)
    embed_model: str | None = Field(default=None, max_length=200)


class SaveIn(ProbeIn):
    chat_model: str = Field(min_length=1, max_length=200)
    embed_model: str = Field(min_length=1, max_length=200)


def _mask(key: str) -> str | None:
    return "…" + key[-4:] if key else None


def _probe_cfg(body: ProbeIn, db) -> dict:
    return llm.config(body.provider, (body.api_key or "").strip() or None, body.chat_model, body.embed_model, db=db)


@router.get("")
def get_settings(_: User = Depends(require("husband")), db=Depends(get_db)):
    cfg = llm.config(db=db)
    return {"provider": cfg["provider"], "chat_model": cfg["chat_model"], "embed_model": cfg["embed_model"],
            "providers": [{"id": k, "name": p["name"], "chat": p["chat"], "embed": p["embed"]}
                          for k, p in llm.PROVIDERS.items()],
            "keys": {k: _mask(llm.config(k, db=db)["api_key"]) for k in llm.PROVIDERS}}


@router.post("/models")
def models(body: ProbeIn, _: User = Depends(require("husband")), db=Depends(get_db)):
    try:
        return llm.list_models(_probe_cfg(body, db))
    except openai.OpenAIError as e:
        raise HTTPException(502, f"{type(e).__name__}: {str(e)[:300]}")


@router.post("/test")
def test(body: ProbeIn, _: User = Depends(require("husband")), db=Depends(get_db)):
    return llm.check(_probe_cfg(body, db))


@router.put("")
def save(body: SaveIn, user: User = Depends(require("husband")), db=Depends(get_db)):
    before = llm.config(db=db)
    row = db.get(Setting, "llm")
    value = dict(row.value) if row else {}
    keys = dict(value.get("keys") or {})
    key_changed = bool(body.api_key and body.api_key.strip())
    if key_changed:
        keys[body.provider] = body.api_key.strip()
    value = {**value, "provider": body.provider, "chat_model": body.chat_model,
             "embed_model": body.embed_model, "keys": keys}
    if row:
        row.value = value
    else:
        db.add(Setting(key="llm", value=value))

    # Другая модель эмбеддингов — другое пространство векторов: старый индекс сбрасываем,
    # он пересчитается при следующей разметке (pipeline.ensure_embeddings).
    reindex = (before["provider"], before["embed_model"]) != (body.provider, body.embed_model)
    if reindex:
        db.execute(delete(VersionEmbedding))
        db.execute(update(Correction).values(embedding=None))
    journal.append(db, "llm_settings_changed", user.id, "settings:llm",
                   {"provider": body.provider, "chat_model": body.chat_model, "embed_model": body.embed_model,
                    "key_changed": key_changed, "reindex": reindex})
    db.commit()
    return {**get_settings(user, db), "reindex": reindex}
