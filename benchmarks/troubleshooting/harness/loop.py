"""The measured tool loop for one trial (design OA02-OA06, R34-R43).

Per iteration:
  1. check limits (time, inference calls, tool calls, cancellation);
  2. count the exact pending input via /v1/responses/input_tokens (purpose=preflight, logged
     separately, never added to solving totals);
  3. compute max_output_tokens = min(8192, 100000 - observed_total - counted_input); stop
     without sending when fewer than 1024 output tokens remain (R36, V07);
  4. reserve worst-case cost with the budget gate; stop on refusal (R58);
  5. open a ledger row (status sent) *before* the POST; send with X-Client-Request-Id;
  6. persist the raw response JSON and usage, validate invariants, model, and tier; only then
  7. append the complete output items to history and execute at most the returned function
     calls, recording every tool event; the submit tool ends the trial.

History is explicit and complete; previous_response_id is never used. Reasoning items are
carried verbatim (never decoded). No retries: any transport/API error terminates the trial.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from .accounting import (AttemptUsage, PricingProfile, UsageError, aggregate, output_budget, parse_usage,
                         request_cost_usd, reserve_usd)
from .budget import BudgetExceeded, BudgetGate, RunCancelled
from .inference import CreateResult, InferenceError, ModelSettings, build_payload
from .ledger import RequestLedger, ToolEventLog, now_iso
from .tools import SUBMISSION_FIELDS, TOOL_SCHEMAS, ToolExecutor

TEXT_ONLY_NUDGE = ("Your last turn contained no tool call. If you are finished, call submit_diagnosis with all "
                   "six fields; otherwise continue investigating with the tools.")


@dataclass(frozen=True)
class Limits:
    max_inference_calls: int = 40
    max_tool_calls: int = 40
    max_seconds: float = 720.0
    token_cap: int = 100_000
    max_output_per_call: int = 8_192
    output_floor: int = 1_024
    per_call_timeout: float = 120.0
    tool_output_cap: int = 16 * 1024
    text_only_nudges: int = 1

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class TrialContext:
    trial_id: str
    trial_dir: Path
    workspace: Path
    vault: Path
    arm: str
    case: str
    model_settings: ModelSettings
    profile: PricingProfile
    limits: Limits
    instructions: str
    initial_input: str
    secrets: list = field(default_factory=list)
    tool_schemas: list = field(default_factory=lambda: list(TOOL_SCHEMAS))
    submit_tool: str = "submit_diagnosis"
    submit_fields: tuple = SUBMISSION_FIELDS


class TrialRunner:
    def __init__(self, ctx: TrialContext, client, budget: BudgetGate, tool_executor: ToolExecutor | None = None):
        self.ctx = ctx
        self.client = client
        self.budget = budget
        self.ledger = RequestLedger(ctx.trial_dir, ctx.trial_id, ctx.secrets)
        self.events = ToolEventLog(ctx.trial_dir, ctx.secrets)
        self.tools = tool_executor or ToolExecutor(ctx.trial_dir, ctx.workspace, ctx.vault, ctx.arm, ctx.case,
                                                   ctx.limits.tool_output_cap)
        self.history: list[dict] = [{"role": "user", "content": ctx.initial_input}]
        self.observed_total = 0
        self.inference_calls = 0
        self.tool_calls = 0
        self.nudges = 0
        self.started = time.monotonic()
        self.stop_reason: str | None = None
        self.stop_detail: str | None = None
        self.submission: dict | None = None
        self.attempts: list[AttemptUsage] = []
        self.pause_batch = False
        self.final_text: str | None = None

    # -- helpers -------------------------------------------------------------------------
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def remaining_time(self) -> float:
        return self.ctx.limits.max_seconds - self.elapsed()

    def stop(self, reason: str, detail: str | None = None, pause: bool = False) -> None:
        self.stop_reason, self.stop_detail = reason, detail
        self.pause_batch = self.pause_batch or pause

    def check_limits(self) -> bool:
        limits = self.ctx.limits
        if self.budget.cancelled:
            self.stop("cancelled", "run cancelled by operator")
        elif self.remaining_time() <= 0:
            self.stop("time_limit", f"{limits.max_seconds}s elapsed")
        elif self.inference_calls >= limits.max_inference_calls:
            self.stop("inference_limit", f"{limits.max_inference_calls} inference calls")
        elif self.tool_calls >= limits.max_tool_calls:
            self.stop("tool_limit", f"{limits.max_tool_calls} tool calls")
        return self.stop_reason is None

    # -- one inference round -------------------------------------------------------------
    def count_pending_input(self) -> int | None:
        settings = self.ctx.model_settings
        payload = build_payload(settings, self.ctx.instructions, self.history, self.ctx.tool_schemas, None)
        row = self.ledger.open_attempt("preflight", payload, settings.model)
        deadline = max(1.0, min(self.ctx.limits.per_call_timeout, self.remaining_time()))
        started = time.monotonic()
        try:
            count = self.client.count_input(settings, self.ctx.instructions, self.history, self.ctx.tool_schemas,
                                            deadline, row["client_request_id"])
        except InferenceError as exc:
            self.ledger.close_attempt(row, status="error", telemetry="not_applicable", failure_reason=f"{exc.kind}: {exc}",
                                      http_status=exc.status_code, server_request_id=exc.request_id,
                                      elapsed_seconds=time.monotonic() - started)
            self.stop("count_error", f"{exc.kind}: {exc}", pause=exc.kind in ("api_status", "other"))
            return None
        self.ledger.close_attempt(row, status="completed", response_json=count.raw, http_status=count.http_status,
                                  server_request_id=count.request_id, telemetry="not_applicable",
                                  derived={"counted_input_tokens": count.input_tokens},
                                  elapsed_seconds=time.monotonic() - started)
        return count.input_tokens

    def inference_round(self) -> CreateResult | None:
        limits, settings, profile = self.ctx.limits, self.ctx.model_settings, self.ctx.profile
        counted = self.count_pending_input()
        if counted is None:
            return None
        max_output = output_budget(self.observed_total, counted, limits.token_cap, limits.max_output_per_call,
                                   limits.output_floor, profile.context_window)
        if max_output is None:
            self.stop("token_limit", f"observed {self.observed_total} + pending input {counted} leaves fewer than "
                                     f"{limits.output_floor} output tokens under the {limits.token_cap} cap")
            return None
        reserve = reserve_usd(counted, max_output, profile)
        payload = build_payload(settings, self.ctx.instructions, self.history, self.ctx.tool_schemas, max_output)
        client_request_id = str(uuid.uuid4())
        attempt_id_preview = str(uuid.uuid4())
        try:
            self.budget.admit(reserve, "solving", attempt_id_preview)
        except RunCancelled as exc:
            self.stop("cancelled", str(exc))
            return None
        except BudgetExceeded as exc:
            self.stop("budget_cap", str(exc), pause=True)
            return None
        row = self.ledger.open_attempt("solving", payload, settings.model, client_request_id, reserve, profile.id,
                                       extra={"counted_input_tokens": counted, "max_output_tokens": max_output})
        deadline = max(1.0, min(limits.per_call_timeout, self.remaining_time()))
        started = time.monotonic()
        try:
            result = self.client.create(payload, deadline, client_request_id)
        except InferenceError as exc:
            elapsed = time.monotonic() - started
            self.inference_calls += 1
            if exc.kind == "timeout":
                # A timeout does not establish zero billing: usage unknown, reserve held (OA05, V04).
                self.ledger.close_attempt(row, status="timeout", telemetry="unknown", failure_reason=str(exc),
                                          server_request_id=exc.request_id, elapsed_seconds=elapsed)
                self.budget.hold_unresolved(reserve, "solving", row["attempt_id"], "timeout without terminal usage")
                self.attempts.append(AttemptUsage(row["attempt_id"], "solving", None, "timeout", None, reserve))
                self.stop("transport_error", f"timeout: {exc}", pause=False)
            else:
                self.ledger.close_attempt(row, status="error", telemetry="unknown", failure_reason=f"{exc.kind}: {exc}",
                                          http_status=exc.status_code, server_request_id=exc.request_id,
                                          elapsed_seconds=elapsed)
                if exc.kind == "connection":
                    self.budget.hold_unresolved(reserve, "solving", row["attempt_id"], "connection error; billing unknown")
                    self.attempts.append(AttemptUsage(row["attempt_id"], "solving", None, "error", None, reserve))
                else:
                    # Server answered with an error status and no usage: nothing generated, reserve released.
                    self.budget.release(reserve, "solving", row["attempt_id"], f"HTTP {exc.status_code} without usage")
                    self.attempts.append(AttemptUsage(row["attempt_id"], "solving", None, "error", None, None))
                self.stop("transport_error" if exc.kind == "connection" else "api_error", f"{exc.kind}: {exc}",
                          pause=exc.kind in ("api_status", "other"))
            return None
        elapsed = time.monotonic() - started
        self.inference_calls += 1
        # Persist first (OA06), then validate.
        usage_error = None
        usage = None
        try:
            usage = parse_usage(result.usage, profile)
        except UsageError as exc:
            usage_error = str(exc)
        cost = request_cost_usd(usage, profile) if usage else None
        self.ledger.close_attempt(
            row, status=result.status or "unknown", response_json=result.raw, http_status=result.http_status,
            server_request_id=result.request_id, response_id=result.response_id, returned_model=result.model,
            returned_tier=result.service_tier, raw_usage=result.usage, derived=usage.as_dict() if usage else None,
            cost_usd=cost, telemetry="complete" if usage else "invalid", failure_reason=usage_error,
            incomplete_reason=result.incomplete_reason, elapsed_seconds=elapsed)
        if usage is None:
            self.budget.hold_unresolved(reserve, "solving", row["attempt_id"], f"usage invalid: {usage_error}")
            self.attempts.append(AttemptUsage(row["attempt_id"], "solving", None, result.status or "unknown", None, reserve))
            self.stop("usage_invalid", usage_error, pause=True)
            return None
        self.budget.settle(reserve, cost, "solving", row["attempt_id"])
        self.attempts.append(AttemptUsage(row["attempt_id"], "solving", usage, result.status or "completed", cost, reserve))
        self.observed_total += usage.request_total
        if counted != usage.input_tokens:
            # Not fatal by itself, but the design asks for investigation of count mismatches.
            self.events.record({"tool": "_count_mismatch", "kind": "telemetry", "counted": counted,
                                "actual": usage.input_tokens, "attempt_id": row["attempt_id"]})
        if not model_matches(settings.model, result.model) or (result.service_tier not in (None, "default")):
            self.stop("protocol_violation", f"returned model {result.model!r} tier {result.service_tier!r}", pause=True)
            return None
        return result

    # -- tool execution -----------------------------------------------------------------
    def run_tool_call(self, call: dict) -> bool:
        """Execute one function call and append its output. Returns True when the trial should stop."""
        name = call.get("name", "")
        try:
            arguments = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError as exc:
            arguments = None
            error = f"arguments were not valid JSON: {exc}"
        self.tool_calls += 1
        started_at = now_iso()
        if arguments is None:
            output = error
            self.events.record({"tool": name, "kind": "other", "call_id": call.get("call_id"), "arguments": call.get("arguments"),
                                "started_at": started_at, "ended_at": now_iso(), "exit_code": None, "error": error})
        elif name == self.ctx.submit_tool:
            self.submission = {field_name: str(arguments.get(field_name, "")) for field_name in self.ctx.submit_fields}
            self.events.record({"tool": name, "kind": "submit", "call_id": call.get("call_id"), "arguments": self.submission,
                                "started_at": started_at, "ended_at": now_iso(), "exit_code": 0})
            write_submission(self.ctx.trial_dir, self.submission)
            output = "Submission received. The trial is complete."
            self.history.append({"type": "function_call_output", "call_id": call["call_id"], "output": output})
            self.stop("submitted")
            return True
        else:
            result = self.tools.execute(name, arguments)
            output = result.output
            self.events.record({"tool": name, "kind": result.kind, "call_id": call.get("call_id"), "arguments": arguments,
                                "started_at": started_at, "ended_at": now_iso(), "exit_code": result.exit_code,
                                "elapsed_seconds": result.elapsed_seconds, "delivered_bytes": len(output.encode()),
                                "truncated": result.truncated, **{f"extra_{k}": v for k, v in result.extra.items()}},
                               raw_output=result.raw_output)
        self.history.append({"type": "function_call_output", "call_id": call["call_id"], "output": output})
        return False

    # -- main loop ----------------------------------------------------------------------
    def run(self) -> dict:
        try:
            while self.check_limits():
                result = self.inference_round()
                if result is None:
                    break
                self.history.extend(result.output)      # complete items, reasoning included, verbatim
                if result.status == "incomplete":
                    self.final_text = result.output_text() or None
                    self.stop("generation_limit", result.incomplete_reason or "incomplete")
                    break
                if result.status not in (None, "completed"):
                    self.stop("api_error", f"response status {result.status}", pause=True)
                    break
                calls = result.function_calls()
                if not calls:
                    text = result.output_text()
                    if result.has_refusal():
                        self.final_text = text
                        self.stop("refusal")
                        break
                    if self.nudges < self.ctx.limits.text_only_nudges:
                        self.nudges += 1
                        self.history.append({"role": "user", "content": TEXT_ONLY_NUDGE})
                        self.events.record({"tool": "_nudge", "kind": "harness", "text": TEXT_ONLY_NUDGE})
                        continue
                    self.final_text = text
                    self.stop("submitted_text", "final assistant message without submit tool")
                    write_submission(self.ctx.trial_dir, {"free_text": text})
                    break
                stop = False
                for call in calls:
                    if self.tool_calls >= self.ctx.limits.max_tool_calls:
                        self.stop("tool_limit", f"{self.ctx.limits.max_tool_calls} tool calls")
                        stop = True
                        break
                    if self.run_tool_call(call):
                        stop = True
                        break
                if stop:
                    break
        except Exception as exc:  # noqa: BLE001 - harness fault must still leave a record
            self.stop("harness_error", f"{type(exc).__name__}: {exc}", pause=True)
        return self.write_summary()

    def write_summary(self) -> dict:
        totals = aggregate(self.attempts, "solving")
        events = self.events.events()
        summary = {
            "trial_id": self.ctx.trial_id, "arm": self.ctx.arm, "case": self.ctx.case,
            "model": self.ctx.model_settings.model, "stop_reason": self.stop_reason, "stop_detail": self.stop_detail,
            "pause_batch": self.pause_batch, "submitted": self.submission is not None,
            "submitted_text": self.stop_reason == "submitted_text",
            "elapsed_seconds": round(self.elapsed(), 3), "inference_calls": self.inference_calls,
            "tool_calls": self.tool_calls, "nudges": self.nudges,
            "reproductions": sum(1 for e in events if e.get("tool") == "reproduce_incident"),
            "telemetry_complete": totals.usage_complete, "usage_complete": totals.usage_complete,
            "exact_total_tokens": totals.exact_total, "known_token_lower_bound": totals.known_lower_bound,
            "missing_attempt_ids": totals.missing_attempt_ids,
            "subtotals": {"input_tokens": totals.input_tokens, "output_tokens": totals.output_tokens,
                          "cached_tokens": totals.cached_tokens, "cache_write_tokens": totals.cache_write_tokens,
                          "reasoning_tokens": totals.reasoning_tokens, "ordinary_input": totals.ordinary_input,
                          "non_reasoning_output": totals.non_reasoning_output},
            "estimated_cost_usd": None if totals.estimated_cost_usd is None else str(totals.estimated_cost_usd),
            "known_cost_usd": str(totals.known_cost_usd), "unresolved_reserve_usd": str(totals.unresolved_reserve_usd),
            "pricing_profile_id": self.ctx.profile.id, "limits": self.ctx.limits.as_dict(),
            "action_counts": action_counts(events), "finished_at": now_iso(),
        }
        (self.ctx.trial_dir / "summary.json").write_text(json.dumps(summary, indent=2))
        return summary


def model_matches(requested: str, returned: str | None) -> bool:
    if not returned:
        return False
    return returned == requested or returned.startswith(requested + "-")


def write_submission(trial_dir: Path, submission: dict) -> None:
    lines = ["# Submission", ""]
    for key, value in submission.items():
        lines += [f"## {key}", "", str(value), ""]
    (trial_dir / "submission.md").write_text("\n".join(lines))
    (trial_dir / "submission.json").write_text(json.dumps(submission, indent=2))


def action_counts(events: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for event in events:
        if str(event.get("tool", "")).startswith("_"):
            continue
        kind = event.get("kind", "other")
        counts[kind] = counts.get(kind, 0) + 1
    return counts
