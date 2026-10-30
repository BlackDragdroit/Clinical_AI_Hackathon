import base64
import json

import httpx
import pytest

from app import llm
from app.config import settings

SCHEMA = {"type": "object", "properties": {"inr": {"type": "number"}}, "required": ["inr"]}
MSG = [{"role": "user", "content": "INR 1.0"}]


@pytest.fixture
def cfg():
    """settings is frozen: set a field the way conftest does and put it back afterwards."""
    old = {}

    def set_(name, value):
        old.setdefault(name, getattr(settings, name))
        object.__setattr__(settings, name, value)

    yield set_
    for name, value in old.items():
        object.__setattr__(settings, name, value)


def _serve(monkeypatch, content=None, status=200):
    seen = {}

    def post(url, json=None, headers=None, timeout=None):  # noqa: A002 - mirrors httpx.post
        seen.update(url=url, body=json, headers=headers, timeout=timeout)
        req = httpx.Request("POST", url)
        body = {"choices": [{"message": {"content": content}}]}
        return httpx.Response(status, json=body, request=req)

    monkeypatch.setattr(llm.httpx, "post", post)
    return seen


def test_sends_strict_schema_and_parses_json(monkeypatch):
    seen = _serve(monkeypatch, '{"inr": 1.0}')
    assert llm.complete_json(SCHEMA, MSG) == {"inr": 1.0}
    assert seen["url"] == f"{settings.llm_base_url}/chat/completions"
    assert seen["body"]["model"] == settings.llm_model and seen["body"]["temperature"] == 0
    assert seen["body"]["response_format"]["json_schema"] == {"name": "out", "schema": SCHEMA, "strict": True}
    assert seen["headers"] == {}   # no key configured -> no Authorization header


def test_sends_bearer_token_when_configured(monkeypatch, cfg):
    seen = _serve(monkeypatch, '{"inr": 1.0}')
    cfg("llm_api_key", "k")
    llm.complete_json(SCHEMA, MSG)
    assert seen["headers"] == {"Authorization": "Bearer k"}


def test_strips_code_fence(monkeypatch):
    _serve(monkeypatch, '```json\n{"inr": 1.0}\n```')
    assert llm.complete_json(SCHEMA, MSG) == {"inr": 1.0}


@pytest.mark.parametrize("content,status", [("not json", 200), (None, 200), ('{"inr": 1}', 500)])
def test_bad_answers_raise_llmerror(monkeypatch, content, status):
    _serve(monkeypatch, content, status)
    with pytest.raises(llm.LLMError):
        llm.complete_json(SCHEMA, MSG)


def test_unreachable_server_raises_llmerror(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm.httpx, "post", boom)
    with pytest.raises(llm.LLMError):
        llm.complete_json(SCHEMA, MSG)


def test_unknown_provider_is_refused_without_a_request(monkeypatch, cfg):
    seen = _serve(monkeypatch, "{}")
    cfg("llm_provider", "anthropic")
    with pytest.raises(llm.LLMError):
        llm.complete_json(SCHEMA, MSG)
    assert not seen


def test_image_message_inlines_the_image():
    m = llm.image_message("lies das", b"\x89PNG")
    assert m["content"][0] == {"type": "text", "text": "lies das"}
    assert m["content"][1]["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode()
    json.dumps(m)   # must be serialisable as-is
