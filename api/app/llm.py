"""OpenAI-совместимый клиент. Провайдер, модели и ключ — из настроек (таблица settings), иначе из .env."""

import os
import time
from typing import TypeVar

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel

from .db import Session
from .models import EMBED_DIM, Setting

PROVIDERS = {
    "openai": {"name": "OpenAI", "base_url": None, "env_key": "OPENAI_API_KEY",
               "chat": "gpt-4.1-mini", "embed": "text-embedding-3-small"},
    "gemini": {"name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "env_key": "GEMINI_API_KEY", "chat": "gemini-3.8-flash", "embed": "gemini-embedding-001"},
}

T = TypeVar("T", bound=BaseModel)
_clients: dict[tuple, OpenAI] = {}


def stored(db=None) -> dict:
    if db is None:
        with Session() as own:
            return stored(own)
    row = db.get(Setting, "llm")
    return dict(row.value) if row else {}


def config(provider: str | None = None, api_key: str | None = None, chat_model: str | None = None,
           embed_model: str | None = None, db=None) -> dict:
    """Действующие настройки; аргументы подменяют сохранённое (для проверки до сохранения)."""
    s = stored(db)
    provider = provider or s.get("provider") or "openai"
    p = PROVIDERS[provider]
    same = provider == (s.get("provider") or "openai")
    env_chat = os.environ.get("LLM_MODEL") if provider == "openai" else None
    env_embed = os.environ.get("EMBED_MODEL") if provider == "openai" else None
    return {
        "provider": provider,
        "api_key": api_key or (s.get("keys") or {}).get(provider) or os.environ.get(p["env_key"], ""),
        "base_url": p["base_url"] or (os.environ.get("OPENAI_BASE_URL") or None),
        "chat_model": chat_model or (same and s.get("chat_model")) or env_chat or p["chat"],
        "embed_model": embed_model or (same and s.get("embed_model")) or env_embed or p["embed"],
    }


def _client(cfg: dict) -> OpenAI:
    if not cfg["api_key"]:
        raise HTTPException(503, f"LLM не настроен: укажите API-ключ {PROVIDERS[cfg['provider']]['name']} в настройках")
    k = (cfg["base_url"], cfg["api_key"])
    if k not in _clients:
        _clients[k] = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=60, max_retries=2)
    return _clients[k]


def _embed_raw(texts: list[str], cfg: dict) -> list[list[float]]:
    r = _client(cfg).embeddings.create(model=cfg["embed_model"], input=texts)
    vecs = [d.embedding for d in r.data]
    if vecs and len(vecs[0]) < EMBED_DIM:
        raise HTTPException(502, f"Модель {cfg['embed_model']} даёт {len(vecs[0])} измерений, нужно не меньше {EMBED_DIM}")
    return vecs


def embed(texts: list[str], cfg: dict | None = None) -> list[list[float]]:
    # Усечение до EMBED_DIM верно для MRL-моделей (OpenAI text-embedding-3, Gemini embedding);
    # поиск идёт по косинусу, поэтому нормировать после усечения не нужно.
    return [v[:EMBED_DIM] for v in _embed_raw(texts, cfg or config())]


def ask(system: str, examples: list[tuple[str, str]], user: str, schema: type[T], cfg: dict | None = None) -> T:
    """Один вызов со structured output. examples — пары (вопрос, правильный ответ JSON) для few-shot."""
    cfg = cfg or config()
    messages = [{"role": "system", "content": system}]
    for q, a in examples:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": user})
    r = _client(cfg).chat.completions.parse(model=cfg["chat_model"], messages=messages, response_format=schema,
                                            temperature=0.2)
    msg = r.choices[0].message
    if msg.parsed is None:
        raise HTTPException(502, f"LLM ответил не по схеме: {msg.refusal or 'пустой ответ'}")
    return msg.parsed


_NOT_CHAT = ("embed", "tts", "audio", "realtime", "transcribe", "image", "imagen", "veo", "whisper", "dall-e",
             "moderation", "search", "computer-use", "live", "babbage", "davinci", "aqa")


def list_models(cfg: dict) -> dict:
    ids = sorted({m.id.removeprefix("models/") for m in _client(cfg).models.list()})
    return {"chat": [i for i in ids if not any(x in i for x in _NOT_CHAT)],
            "embed": [i for i in ids if "embed" in i]}


class _Ping(BaseModel):
    ok: bool


def _timed(fn) -> dict:
    t = time.monotonic()
    try:
        extra = fn() or {}
        return {"ok": True, "ms": round((time.monotonic() - t) * 1000), **extra}
    except HTTPException as e:
        return {"ok": False, "error": e.detail}
    except Exception as e:  # ошибки провайдера показываем как есть: это экран диагностики
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


def check(cfg: dict) -> dict:
    """Проверка соединения: короткий вызов со structured output и один эмбеддинг."""
    return {
        "chat": _timed(lambda: {"model": cfg["chat_model"],
                                "answer": ask("Ответь ok=true.", [], "Проверка связи", _Ping, cfg).ok}),
        "embed": _timed(lambda: {"model": cfg["embed_model"], "dims": len(_embed_raw(["проверка"], cfg)[0])}),
    }
