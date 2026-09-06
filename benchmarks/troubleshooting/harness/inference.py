"""Thin wrapper over the pinned openai SDK for the Responses API (design OA01-OA06).

Fixed per-request settings (OA03): stream=false, store=false, background=false,
service_tier="default", parallel_tool_calls=false, truncation="disabled". Reasoning effort is
pinned to medium; the reasoning-context mode is pinned per manifest when supported. SDK
retries are disabled (max_retries=0) so an injected 429/connection error/timeout produces
exactly one POST (OA05, V09). Every request carries a locally generated X-Client-Request-Id.

The key is passed explicitly; the SDK's environment lookup is never used.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

FIXED_REQUEST_SETTINGS = {"stream": False, "store": False, "background": False, "service_tier": "default",
                          "parallel_tool_calls": False, "truncation": "disabled"}


@dataclass(frozen=True)
class ModelSettings:
    model: str
    reasoning_effort: str = "medium"
    reasoning_context: str | None = None      # "current_turn" | "all_turns" | None (model default)
    include_encrypted_reasoning: bool = True
    reasoning_summary: str | None = None

    def reasoning_param(self) -> dict:
        reasoning = {"effort": self.reasoning_effort}
        if self.reasoning_context:
            reasoning["context"] = self.reasoning_context
        if self.reasoning_summary:
            reasoning["summary"] = self.reasoning_summary
        return reasoning


class InferenceError(Exception):
    def __init__(self, kind: str, message: str, status_code: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.kind = kind                    # connection | timeout | rate_limit | api_status | other
        self.status_code = status_code
        self.request_id = request_id


@dataclass
class CountResult:
    input_tokens: int
    raw: dict
    http_status: int | None
    request_id: str | None


@dataclass
class CreateResult:
    raw: dict
    http_status: int | None
    request_id: str | None
    payload: dict = field(default_factory=dict)

    @property
    def response_id(self) -> str | None:
        return self.raw.get("id")

    @property
    def model(self) -> str | None:
        return self.raw.get("model")

    @property
    def service_tier(self) -> str | None:
        return self.raw.get("service_tier")

    @property
    def status(self) -> str | None:
        return self.raw.get("status")

    @property
    def incomplete_reason(self) -> str | None:
        details = self.raw.get("incomplete_details") or {}
        return details.get("reason")

    @property
    def usage(self) -> dict | None:
        return self.raw.get("usage")

    @property
    def output(self) -> list[dict]:
        return list(self.raw.get("output") or [])

    def function_calls(self) -> list[dict]:
        return [item for item in self.output if item.get("type") == "function_call"]

    def output_text(self) -> str:
        parts = []
        for item in self.output:
            if item.get("type") == "message":
                for content in item.get("content") or []:
                    if content.get("type") in ("output_text", "text") and content.get("text"):
                        parts.append(content["text"])
                    elif content.get("type") == "refusal":
                        parts.append(f"[refusal] {content.get('refusal', '')}")
        return "\n".join(parts)

    def has_refusal(self) -> bool:
        return any(content.get("type") == "refusal" for item in self.output if item.get("type") == "message"
                   for content in item.get("content") or [])


def build_payload(settings: ModelSettings, instructions: str, history: list[dict], tools: list[dict],
                  max_output_tokens: int | None) -> dict:
    payload = {"model": settings.model, "instructions": instructions, "input": history, "tools": tools,
               "tool_choice": "auto", "reasoning": settings.reasoning_param(), **FIXED_REQUEST_SETTINGS}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens
    if settings.include_encrypted_reasoning:
        payload["include"] = ["reasoning.encrypted_content"]
    return payload


def _translate(exc: BaseException) -> InferenceError:
    import openai

    request_id = getattr(exc, "request_id", None)
    if isinstance(exc, openai.APITimeoutError):
        return InferenceError("timeout", str(exc), None, request_id)
    if isinstance(exc, openai.APIConnectionError):
        return InferenceError("connection", str(exc), None, request_id)
    if isinstance(exc, openai.RateLimitError):
        return InferenceError("rate_limit", str(exc), exc.status_code, request_id)
    if isinstance(exc, openai.APIStatusError):
        return InferenceError("api_status", str(exc), exc.status_code, request_id)
    return InferenceError("other", f"{type(exc).__name__}: {exc}", None, request_id)


class ResponsesClient:
    """Host-side inference client. Only this object ever holds the key."""

    def __init__(self, api_key: str, project: str | None = None, timeout: float = 120.0, http_client=None):
        import openai

        if not api_key or not api_key.strip():
            raise ValueError("an explicit OpenAI API key is required")
        kwargs = {"api_key": api_key.strip(), "max_retries": 0, "timeout": timeout}
        if project:
            kwargs["project"] = project
        if http_client is not None:
            kwargs["http_client"] = http_client
        self._client = openai.OpenAI(**kwargs)

    def count_input(self, settings: ModelSettings, instructions: str, history: list[dict], tools: list[dict],
                    timeout: float, client_request_id: str | None = None) -> CountResult:
        client_request_id = client_request_id or str(uuid.uuid4())
        try:
            raw = self._client.responses.input_tokens.with_raw_response.count(
                model=settings.model, instructions=instructions, input=history, tools=tools,
                tool_choice="auto", parallel_tool_calls=False, truncation="disabled",
                reasoning=settings.reasoning_param(), timeout=timeout,
                extra_headers={"X-Client-Request-Id": client_request_id})
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        body = raw.http_response.json()
        return CountResult(int(body["input_tokens"]), body, raw.http_response.status_code,
                           raw.http_response.headers.get("x-request-id"))

    def create(self, payload: dict, timeout: float, client_request_id: str) -> CreateResult:
        try:
            raw = self._client.responses.with_raw_response.create(
                **payload, timeout=timeout, extra_headers={"X-Client-Request-Id": client_request_id})
        except Exception as exc:  # noqa: BLE001
            raise _translate(exc) from exc
        body = raw.http_response.json()
        return CreateResult(body, raw.http_response.status_code, raw.http_response.headers.get("x-request-id"), payload)


def response_to_dict(response) -> dict:
    """Convert a parsed SDK object to a plain dict (only used for tests/fakes)."""
    return json.loads(response.model_dump_json()) if hasattr(response, "model_dump_json") else dict(response)
