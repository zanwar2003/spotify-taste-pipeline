import json

import httpx
import pytest

from tastepipe.agent.llm import LLMOutputError, ProposeContext
from tastepipe.agent.llm_openai import OpenAICompatLLM, make_llm
from tastepipe.agent.models import PlaylistRequest

from fakes import PROFILE  # isort: skip

REQ = PlaylistRequest(source_username="zara", intent="focus", mood="calm", target_minutes=30)
CTX = ProposeContext(REQ, PROFILE, avoid=[], count=5, first_round=True)
VALID = {"playlist_title": "Calm Focus", "suggestions": [{"title": "T", "artist": "A", "reason": "r"}]}


def reply(args, id_="c1"):
    call = {"id": id_, "type": "function", "function": {"name": "x", "arguments": json.dumps(args)}}
    return {"choices": [{"message": {"role": "assistant", "tool_calls": [call]}}]}


def llm(*responses):
    """OpenAICompatLLM wired to a mock transport that serves scripted JSON bodies."""
    queue, seen = list(responses), []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        item = queue.pop(0)
        return httpx.Response(item, json={}) if isinstance(item, int) else httpx.Response(200, json=item)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatLLM(base_url="https://x/v1", api_key="k", model="m", client=client), seen


def test_forces_the_function_call_and_validates_output():
    m, seen = llm(reply(VALID))
    out = m.propose(CTX)
    assert out.suggestions[0].title == "T"
    assert seen[0]["tool_choice"] == {"type": "function", "function": {"name": "submit_suggestions"}}
    assert seen[0]["model"] == "m" and seen[0]["messages"][0]["role"] == "system"


def test_invalid_output_is_retried_once_with_the_error_fed_back():
    m, seen = llm(reply({"suggestions": "nope"}), reply(VALID, "c2"))
    assert m.propose(CTX).playlist_title == "Calm Focus"
    assert seen[1]["messages"][-1]["role"] == "tool"
    assert "Invalid output" in seen[1]["messages"][-1]["content"]


def test_giving_up_raises_a_clear_error():
    m, _ = llm(reply({"suggestions": "nope"}), {"choices": []})
    with pytest.raises(LLMOutputError):
        m.propose(CTX)


def test_http_failure_becomes_llm_error_without_leaking_details():
    m, _ = llm(429)
    with pytest.raises(LLMOutputError, match="HTTPStatusError"):
        m.propose(CTX)


def test_factory_picks_provider_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    made = make_llm()
    assert isinstance(made, OpenAICompatLLM) and "groq.com" in made._url
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        make_llm()
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(RuntimeError, match="unknown"):
        make_llm()
