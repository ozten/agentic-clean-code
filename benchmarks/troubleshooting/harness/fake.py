"""Scripted stand-in for the OpenAI client. Used by dry runs and tests; never by measured trials.

Synthetic usage numbers are artificial test data (design "golden cases"), not measurements.
The dry-run pricing profile uses the design doc's fictional rates.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

from .accounting import PricingProfile
from .inference import CountResult, CreateResult, InferenceError, ModelSettings

FAKE_MODEL = "fake-model"

DRY_RUN_PROFILE = PricingProfile(
    id="fictional/dry-run", snapshot_id="fictional", model=FAKE_MODEL, snapshot=None,
    ordinary_input=Decimal("2"), cached_input=Decimal("0.20"), cache_write=Decimal("2.50"), output=Decimal("10"),
    cache_write_category="priced", long_context_threshold=272_000, context_window=400_000,
    reasoning_efforts=("medium",), doc_url="")

S2_ANSWER = {
    "failed_boundary": "The local confirmation write failed: after the provider returned a transfer, the ledger's "
                       "confirm transaction (UPDATE payments SET transfer_id ...) raised 'database or disk is full' "
                       "and rolled back, so the posting and receipt were never committed.",
    "evidence": "incident/stderr.txt traceback ending in sqlite3.IntegrityError: database or disk is full at the "
                "UPDATE payments statement; incident/ledger.db shows payments row milestone-42 with transfer_id NULL, "
                "balances available=50000 reserved=50000 contractor=0, zero postings; app source confirm().",
    "external_outcome": "The provider returned a transfer response with id tr_demo_500 for idempotency key "
                        "contractor-payment:milestone-42. That shows the provider accepted the transfer; it does not "
                        "prove bank settlement.",
    "local_state": "Payment row present with transfer_id NULL; $500 reserved; no posting; contractor balance 0.",
    "reproduction": "Start from a fresh ledger with 100000 cents; make the confirmation UPDATE fail (e.g. a trigger "
                    "that raises 'database or disk is full' on UPDATE OF transfer_id); run the payment with the success "
                    "fixture; assert exit 1, IntegrityError in stderr, reserved=50000, postings=0, transfer_id NULL.",
    "recovery": "Fix storage; retry the same payment_id with the same amount, destination and idempotency key within "
                "the 23h window; the provider deduplicates and returns tr_demo_500; the app then commits the posting. "
                "Never release the reservation or mint a new payment id while the outcome is unresolved.",
}

DEFAULT_SCRIPT = [
    ("list_files", {"path": ".", "max_depth": 3}),
    ("read_file", {"path": "incident/report.md", "start_line": None, "max_lines": None}),
    ("read_file", {"path": "incident/stderr.txt", "start_line": None, "max_lines": None}),
    ("run_shell", {"command": "sqlite3 incident/ledger.db 'select * from balances; select * from payments; select count(*) from postings;'",
                   "timeout_seconds": None}),
    ("reproduce_incident", {}),
    ("submit_diagnosis", S2_ANSWER),
]


class ScriptedClient:
    """Deterministic fake. `script` is a list of (tool_name, arguments) turns; None = text-only turn."""

    def __init__(self, script=None, *, fail_on_call: dict | None = None, incomplete_on: int | None = None,
                 bad_usage_on: int | None = None, drop_cache_write: bool = False, model: str = FAKE_MODEL,
                 returned_model: str | None = None, tier: str = "default", fixed_output: int = 300,
                 reasoning: int = 200):
        self.script = list(script if script is not None else DEFAULT_SCRIPT)
        self.fail_on_call = fail_on_call or {}
        self.incomplete_on = incomplete_on
        self.bad_usage_on = bad_usage_on
        self.drop_cache_write = drop_cache_write
        self.model = model
        self.returned_model = returned_model or model
        self.tier = tier
        self.fixed_output = fixed_output
        self.reasoning = reasoning
        self.create_calls = 0
        self.count_calls = 0
        self.payloads: list[dict] = []

    def reset(self) -> None:
        """Start a new scripted trial (the scheduler calls this before each trial)."""
        self.create_calls = 0
        self.count_calls = 0
        self.payloads = []

    def _input_estimate(self, history, instructions, tools) -> int:
        return 200 + len(json.dumps(history)) // 4 + len(instructions) // 4 + len(json.dumps(tools)) // 8

    def count_input(self, settings: ModelSettings, instructions, history, tools, timeout, client_request_id=None):
        self.count_calls += 1
        n = self._input_estimate(history, instructions, tools)
        return CountResult(n, {"object": "response.input_tokens", "input_tokens": n}, 200, f"req_count_{self.count_calls}")

    def create(self, payload: dict, timeout: float, client_request_id: str) -> CreateResult:
        self.create_calls += 1
        self.payloads.append(payload)
        n = self.create_calls
        if n in self.fail_on_call:
            failure = self.fail_on_call[n]
            raise failure if isinstance(failure, InferenceError) else InferenceError(*failure)
        input_tokens = self._input_estimate(payload["input"], payload["instructions"], payload["tools"])
        cached = (input_tokens // 2) if n > 1 else 0
        cache_write = 0 if n > 1 else input_tokens // 4
        output = self.fixed_output
        reasoning = min(self.reasoning, output)
        usage = {"input_tokens": input_tokens, "input_tokens_details": {"cached_tokens": cached, "cache_write_tokens": cache_write},
                 "output_tokens": output, "output_tokens_details": {"reasoning_tokens": reasoning},
                 "total_tokens": input_tokens + output}
        if self.drop_cache_write:
            del usage["input_tokens_details"]["cache_write_tokens"]
        if self.bad_usage_on == n:
            usage["total_tokens"] += 1
        turn = self.script[n - 1] if n - 1 < len(self.script) else None
        items = [{"type": "reasoning", "id": f"rs_{uuid.uuid4().hex[:12]}", "summary": [],
                  "encrypted_content": "opaque-" + uuid.uuid4().hex}]
        status = "completed"
        if self.incomplete_on == n:
            status = "incomplete"
            items.append({"type": "message", "id": f"msg_{n}", "role": "assistant", "status": "incomplete",
                          "content": [{"type": "output_text", "text": "partial", "annotations": []}]})
        elif turn is None:
            items.append({"type": "message", "id": f"msg_{n}", "role": "assistant", "status": "completed",
                          "content": [{"type": "output_text", "text": "I have finished looking.", "annotations": []}]})
        else:
            name, arguments = turn
            items.append({"type": "function_call", "id": f"fc_{uuid.uuid4().hex[:12]}", "call_id": f"call_{n}",
                          "name": name, "arguments": json.dumps(arguments), "status": "completed"})
        raw = {"id": f"resp_{uuid.uuid4().hex}", "object": "response", "created_at": 0, "status": status,
               "model": self.returned_model, "service_tier": self.tier, "output": items, "usage": usage,
               "incomplete_details": {"reason": "max_output_tokens"} if status == "incomplete" else None,
               "store": False, "parallel_tool_calls": False, "truncation": "disabled"}
        return CreateResult(raw, 200, f"req_{n}", payload)
