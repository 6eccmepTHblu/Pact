"""OpenAI-совместимый клиент: облачный API или Ollama, меняется через OPENAI_BASE_URL."""

import os
from typing import TypeVar

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel

LLM_MODEL = os.environ.get("LLM_MODEL") or "gpt-4.1-mini"
EMBED_MODEL = os.environ.get("EMBED_MODEL") or "text-embedding-3-small"

T = TypeVar("T", bound=BaseModel)
_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(503, "LLM не настроен: в .env нет OPENAI_API_KEY")
    if _client is None:
        _client = OpenAI(base_url=os.environ.get("OPENAI_BASE_URL") or None, timeout=60, max_retries=2)
    return _client


def embed(texts: list[str]) -> list[list[float]]:
    r = client().embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in r.data]


def ask(system: str, examples: list[tuple[str, str]], user: str, schema: type[T]) -> T:
    """Один вызов со structured output. examples — пары (вопрос, правильный ответ JSON) для few-shot."""
    messages = [{"role": "system", "content": system}]
    for q, a in examples:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": user})
    r = client().chat.completions.parse(model=LLM_MODEL, messages=messages, response_format=schema,
                                        temperature=0.2)
    msg = r.choices[0].message
    if msg.parsed is None:
        raise HTTPException(502, f"LLM ответил не по схеме: {msg.refusal or 'пустой ответ'}")
    return msg.parsed
