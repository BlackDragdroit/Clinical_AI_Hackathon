"""Client for the extraction/OCR model (Ministral 3 8B on vLLM, reached through an SSH tunnel). Owner: SWE 1.

Any OpenAI-compatible server works (vLLM, Ollama, ...): the vendor is replaceable by config alone.
The model's output is untrusted input: it goes through the same matcher and FHIR validation as a parsed document,
never straight to filing.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from app.config import settings


class LLMError(RuntimeError):
    """The model server is unreachable, answered with an error, or returned something that is not the JSON asked for."""


def image_message(prompt: str, image: bytes, mime: str = "image/png") -> dict:
    """One user message with a text part and an inline image, for OCR-style extraction."""
    url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    return {"role": "user", "content": [{"type": "text", "text": prompt},
                                        {"type": "image_url", "image_url": {"url": url}}]}


def complete_json(schema: dict, messages: list[dict], *, name: str = "out") -> dict:
    """Ask the model for JSON that matches `schema` (strict) and return it parsed."""
    if settings.llm_provider not in ("openai_compatible", "openai"):
        raise LLMError(f"LLM_PROVIDER={settings.llm_provider!r} is not implemented (openai_compatible)")
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    body = {"model": settings.llm_model, "temperature": 0, "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}}
    try:
        r = httpx.post(f"{settings.llm_base_url}/chat/completions", json=body, headers=headers,
                       timeout=settings.llm_timeout)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"model call failed: {e}") from e
    if not isinstance(content, str):   # null content: refusal or truncated answer
        raise LLMError(f"model returned no text: {content!r}")
    # a server without schema enforcement may still wrap the JSON in a code fence
    content = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", content)
    try:
        return json.loads(content)
    except ValueError as e:
        raise LLMError(f"model did not return JSON: {content[:200]!r}") from e
