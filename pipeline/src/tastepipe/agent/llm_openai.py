"""Adapter for any OpenAI-compatible chat API (Groq, Gemini, OpenRouter, ...), plus the factory
that picks the provider from the environment.

Same contract as `AnthropicLLM`: every call is a forced tool call, output is validated against a
Pydantic schema, and a validation failure is retried once with the error fed back.
"""

from __future__ import annotations

import json
import os
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .llm import (
    SYSTEM_PROMPT,
    EditContext,
    LLMOutputError,
    ProposeContext,
    ReferenceContext,
    edit_prompt,
    propose_prompt,
    reference_prompt,
)
from .models import EditPlan, ProposeResult, ReferencePicks

T = TypeVar("T", bound=BaseModel)

# provider -> (base URL, default model, env var holding the key)
PROVIDERS: dict[str, tuple[str, str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.5-flash",
        "GEMINI_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "meta-llama/llama-3.3-70b-instruct:free",
        "OPENROUTER_API_KEY",
    ),
}


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        client: httpx.Client | None = None,
    ):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=60)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            res = self._client.post(self._url, json=body, headers=self._headers)
            res.raise_for_status()
            return res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMOutputError(f"model provider request failed: {type(exc).__name__}") from exc

    def _call(self, schema: type[T], tool: str, user: str) -> T:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool,
                    "description": f"Submit the {tool.removeprefix('submit_')} result.",
                    "parameters": schema.model_json_schema(),
                },
            }
        ]
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        last_error = ""
        for _ in range(2):  # one retry with the validation error fed back
            data = self._post(
                {
                    "model": self._model,
                    "max_tokens": 4000,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": {"type": "function", "function": {"name": tool}},
                }
            )
            try:
                message = data["choices"][0]["message"]
                call = message["tool_calls"][0]
                args = json.loads(call["function"]["arguments"])
            except (KeyError, IndexError, TypeError, ValueError):
                last_error = "no usable tool call in response"
                continue
            try:
                return schema.model_validate(args)
            except ValidationError as exc:
                last_error = str(exc)[:500]
                messages = [
                    *messages[:2],
                    {"role": "assistant", "content": None, "tool_calls": [call]},
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", "call_1"),
                        "content": f"Invalid output, fix and resubmit: {last_error}",
                    },
                ]
        raise LLMOutputError(f"{tool}: {last_error}")

    def propose(self, ctx: ProposeContext) -> ProposeResult:
        return self._call(ProposeResult, "submit_suggestions", propose_prompt(ctx))

    def plan_edit(self, ctx: EditContext) -> EditPlan:
        return self._call(EditPlan, "submit_edit", edit_prompt(ctx))

    def pick_from_reference(self, ctx: ReferenceContext) -> ReferencePicks:
        return self._call(ReferencePicks, "submit_picks", reference_prompt(ctx))


def make_llm():
    """LLM_PROVIDER=anthropic (default) | groq | gemini | openrouter | custom.

    custom needs LLM_BASE_URL, LLM_API_KEY and LLM_MODEL. LLM_MODEL overrides any default.
    """
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        from .llm import AnthropicLLM

        return AnthropicLLM()
    if provider == "custom":
        base, default_model, key_var = os.environ.get("LLM_BASE_URL", ""), "", "LLM_API_KEY"
    elif provider in PROVIDERS:
        base, default_model, key_var = PROVIDERS[provider]
    else:
        raise RuntimeError(f"unknown LLM_PROVIDER {provider!r}")
    key = os.environ.get(key_var) or os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL") or default_model
    if not (base and key and model):
        raise RuntimeError(f"LLM_PROVIDER={provider} needs {key_var}, a base URL and a model")
    return OpenAICompatLLM(base_url=base, api_key=key, model=model)
