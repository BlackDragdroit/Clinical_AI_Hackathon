"""Text -> JSON with a small model on vLLM. Output shape is forced by a JSON schema (vLLM structured outputs);
that every string is copied from the input is checked afterwards in engine/ground.py, not trusted here.

Modes:
  nuextract    NuExtract-style template passed as chat_template_kwargs (verbatim-string fields). VERIFY on the GPU box.
  json_schema  any instruct model (Qwen3.5, Gemma 4, Granite): system prompt + response_format json_schema,
               thinking switched off.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from engine.config import settings


@dataclass
class LlmResult:
    data: dict | None
    model: str
    ms: int
    error: str | None = None
    cached: bool = False


def _schema(fields: dict) -> dict:
    """{'name': 'string' | ['enum', ...] | {'array': {...}}} -> JSON schema with every field nullable."""
    props = {}
    for k, t in fields.items():
        if isinstance(t, list):
            props[k] = {"anyOf": [{"type": "string", "enum": t}, {"type": "null"}]}
        elif isinstance(t, dict) and "array" in t:
            props[k] = {"type": "array", "items": _schema(t["array"])}
        else:
            props[k] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {"type": "object", "properties": props, "required": list(fields), "additionalProperties": False}


def _template(fields: dict) -> dict:
    out = {}
    for k, t in fields.items():
        if isinstance(t, list):
            out[k] = t
        elif isinstance(t, dict) and "array" in t:
            out[k] = [_template(t["array"])]
        else:
            out[k] = "verbatim-string"
    return out


def extract(text: str, fields: dict, instructions: str, max_tokens: int = 600,
            url: str | None = None, model: str | None = None, mode: str | None = None) -> LlmResult:
    url, model, mode = url or settings.llm_url, model or settings.llm_model, mode or settings.llm_mode
    if not url:
        return LlmResult(None, "", 0, "no LLM configured")
    body: dict = {"model": model, "temperature": 0, "max_tokens": max_tokens,
                  "response_format": {"type": "json_schema",
                                      "json_schema": {"name": "extraction", "schema": _schema(fields)}}}
    if mode == "nuextract":
        body["messages"] = [{"role": "user", "content": text}]
        body["chat_template_kwargs"] = {"template": json.dumps(_template(fields), ensure_ascii=False),
                                        "enable_thinking": False}
    else:
        body["messages"] = [{"role": "system", "content": instructions}, {"role": "user", "content": text}]
        body["chat_template_kwargs"] = {"enable_thinking": False}
    cache = _cache_path(body)
    if cache and cache.exists():          # same model + prompt + input -> same answer (eval reruns, demo safety)
        c = json.loads(cache.read_text(encoding="utf-8"))
        return LlmResult(c["data"], model, c["ms"], cached=True)
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{url.rstrip('/')}/chat/completions", json=body, headers=headers, timeout=settings.timeout_s)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        out = LlmResult(data if isinstance(data, dict) else None, model, int((time.perf_counter() - t0) * 1000))
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"data": out.data, "ms": out.ms}, ensure_ascii=False), encoding="utf-8")
        return out
    except Exception as e:  # unreachable, timeout, bad JSON: the rules still answer
        return LlmResult(None, model, int((time.perf_counter() - t0) * 1000), f"{type(e).__name__}: {e}"[:200])


def _cache_path(body: dict):
    """ENGINE_LLM_CACHE=<dir> turns on a disk cache keyed by the whole request body."""
    import hashlib
    import os
    from pathlib import Path
    d = os.environ.get("ENGINE_LLM_CACHE")
    if not d:
        return None
    return Path(d) / (hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest() + ".json")
