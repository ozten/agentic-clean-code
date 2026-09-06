"""Exact OpenAI Responses usage accounting and rate-card cost (design R36-R43, accounting contract).

Field mapping (per inference response):

    I = usage.input_tokens                               total input for this response
    C = usage.input_tokens_details.cached_tokens         cache-read subset of I
    W = usage.input_tokens_details.cache_write_tokens    cache-write subset of I (priced for GPT-5.6+)
    O = usage.output_tokens                              all generated tokens, reasoning included
    R = usage.output_tokens_details.reasoning_tokens     reasoning subset of O
    T = usage.total_tokens                               must equal I + O

Derived:
    ordinary_input        = I - C - W
    non_reasoning_output  = O - R
    request_total         = I + O
    trial_total           = sum(request_total) over solving attempts with complete telemetry

C and W are breakdowns of I; R is a breakdown of O. They are never added on top of their
parents. Invariants: nonnegative integers (bools rejected); C + W <= I; R <= O; T == I + O.
A missing I, O, or T, or a violated invariant, raises UsageError and stops scheduling.
A missing W is accepted only when the pricing profile declares cache_write_category="none"
(older models with no separate cache-write price); that normalization is recorded explicitly.
Missing usage is never zero: the attempt becomes `usage_unknown` and the trial loses its
exact total, keeping only a known lower bound.

Cost (rate-card estimate, not an invoice), Decimal arithmetic:
    request_cost = ((I-C-W)*ordinary + C*cached + W*cache_write + O*output) / 1e6
Reasoning is inside O and carries no second charge.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

MILLION = Decimal(1_000_000)
TRIAL_TOKEN_CAP = 100_000
MAX_OUTPUT_PER_CALL = 8_192
MIN_OUTPUT_FLOOR = 1_024


class UsageError(ValueError):
    """Usage violates the accounting contract; the batch must pause for investigation."""


@dataclass(frozen=True)
class PricingProfile:
    id: str
    snapshot_id: str
    model: str
    snapshot: str | None
    ordinary_input: Decimal
    cached_input: Decimal
    cache_write: Decimal
    output: Decimal
    cache_write_category: str          # "priced" | "none"
    long_context_threshold: int | None
    context_window: int | None
    reasoning_efforts: tuple[str, ...]
    doc_url: str

    @property
    def max_input_rate(self) -> Decimal:
        return max(self.ordinary_input, self.cached_input, self.cache_write)


def load_pricing(path: Path) -> dict[str, PricingProfile]:
    data = json.loads(path.read_text())
    profiles = {}
    for key, raw in data["profiles"].items():
        rates = raw["usd_per_million"]
        long_context = raw.get("long_context")
        profiles[key] = PricingProfile(
            id=f"{data['snapshot_id']}/{key}", snapshot_id=data["snapshot_id"], model=raw["model"],
            snapshot=raw.get("snapshot"), ordinary_input=Decimal(rates["ordinary_input"]),
            cached_input=Decimal(rates["cached_input"]), cache_write=Decimal(rates["cache_write"]),
            output=Decimal(rates["output"]), cache_write_category=raw["cache_write_category"],
            long_context_threshold=long_context["input_threshold_tokens"] if long_context else None,
            context_window=raw.get("context_window"), reasoning_efforts=tuple(raw.get("reasoning_efforts", ())),
            doc_url=raw.get("doc_url", ""))
    return profiles


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    cache_write_normalized: bool = False   # True only under the verified legacy W=0 branch

    @property
    def ordinary_input(self) -> int:
        return self.input_tokens - self.cached_tokens - self.cache_write_tokens

    @property
    def non_reasoning_output(self) -> int:
        return self.output_tokens - self.reasoning_tokens

    @property
    def request_total(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict:
        data = asdict(self)
        data.update(ordinary_input=self.ordinary_input, non_reasoning_output=self.non_reasoning_output,
                    request_total=self.request_total)
        return data


def _counter(raw: dict, path: tuple[str, ...], required: bool) -> int | None:
    node = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            if required:
                raise UsageError(f"usage is missing required counter {'.'.join(path)}")
            return None
        node = node[key]
    if isinstance(node, bool) or not isinstance(node, int):
        raise UsageError(f"usage counter {'.'.join(path)} must be an integer, got {node!r}")
    if node < 0:
        raise UsageError(f"usage counter {'.'.join(path)} is negative: {node}")
    return node


def parse_usage(raw: dict | None, profile: PricingProfile | None = None) -> Usage:
    """Validate a raw `usage` object. Raises UsageError; never returns a guessed value."""
    if not raw:
        raise UsageError("usage object is missing")
    I = _counter(raw, ("input_tokens",), True)
    O = _counter(raw, ("output_tokens",), True)
    T = _counter(raw, ("total_tokens",), True)
    C = _counter(raw, ("input_tokens_details", "cached_tokens"), True)
    R = _counter(raw, ("output_tokens_details", "reasoning_tokens"), True)
    W = _counter(raw, ("input_tokens_details", "cache_write_tokens"), False)
    normalized = False
    if W is None:
        if profile is not None and profile.cache_write_category == "none":
            W, normalized = 0, True   # verified legacy branch: no separate cache-write category exists
        else:
            raise UsageError("usage is missing input_tokens_details.cache_write_tokens and the pricing "
                             "profile does not establish that the model has no cache-write category")
    if C + W > I:
        raise UsageError(f"cached ({C}) + cache_write ({W}) exceed input_tokens ({I})")
    if R > O:
        raise UsageError(f"reasoning_tokens ({R}) exceed output_tokens ({O})")
    if T != I + O:
        raise UsageError(f"total_tokens ({T}) != input_tokens + output_tokens ({I + O})")
    return Usage(I, C, W, O, R, T, normalized)


def request_cost_usd(usage: Usage, profile: PricingProfile) -> Decimal:
    if profile.long_context_threshold is not None and usage.input_tokens > profile.long_context_threshold:
        raise UsageError("request falls in the long-context pricing bracket, which this calculator does not support")
    cost = (Decimal(usage.ordinary_input) * profile.ordinary_input
            + Decimal(usage.cached_tokens) * profile.cached_input
            + Decimal(usage.cache_write_tokens) * profile.cache_write
            + Decimal(usage.output_tokens) * profile.output) / MILLION
    return cost


def reserve_usd(counted_input: int, max_output_tokens: int, profile: PricingProfile,
                counting_allowance: Decimal = Decimal("0")) -> Decimal:
    """Worst-case reservation before a POST: all input at the highest input-category rate."""
    return (Decimal(counted_input) * profile.max_input_rate
            + Decimal(max_output_tokens) * profile.output) / MILLION + counting_allowance


def output_budget(observed_total: int, counted_input: int, cap: int = TRIAL_TOKEN_CAP,
                  max_output: int = MAX_OUTPUT_PER_CALL, floor: int = MIN_OUTPUT_FLOOR,
                  context_window: int | None = None) -> int | None:
    """max_output_tokens for the next call, or None when the call must not be sent (R36, V07)."""
    remaining = cap - observed_total
    allowance = min(max_output, remaining - counted_input)
    if allowance < floor:
        return None
    if context_window is not None and counted_input + allowance > context_window:
        allowance = context_window - counted_input
        if allowance < floor:
            return None
    return allowance


@dataclass
class AttemptUsage:
    """One inference attempt as seen by aggregation. usage=None means unknown, never zero."""
    attempt_id: str
    purpose: str
    usage: Usage | None
    status: str = "completed"     # completed | incomplete | error | timeout | refusal
    cost_usd: Decimal | None = None
    reserve_usd: Decimal | None = None


@dataclass
class Totals:
    attempts: int = 0
    attempts_with_usage: int = 0
    usage_complete: bool = True
    exact_total: int | None = 0
    known_lower_bound: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    cached_tokens: int | None = 0
    cache_write_tokens: int | None = 0
    reasoning_tokens: int | None = 0
    ordinary_input: int | None = 0
    non_reasoning_output: int | None = 0
    known_cost_usd: Decimal = Decimal("0")
    estimated_cost_usd: Decimal | None = Decimal("0")
    unresolved_reserve_usd: Decimal = Decimal("0")
    missing_attempt_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        data = asdict(self)
        for key in ("known_cost_usd", "estimated_cost_usd", "unresolved_reserve_usd"):
            value = data[key]
            data[key] = None if value is None else str(value)
        return data


def aggregate(attempts: list[AttemptUsage], purpose: str = "solving") -> Totals:
    """Sum solving attempts once each by attempt_id (V01, V03, V04). Unknown usage voids exact totals."""
    totals = Totals()
    seen: set[str] = set()
    for attempt in attempts:
        if attempt.purpose != purpose or attempt.attempt_id in seen:
            continue
        seen.add(attempt.attempt_id)
        totals.attempts += 1
        usage = attempt.usage
        if usage is None:
            totals.usage_complete = False
            totals.missing_attempt_ids.append(attempt.attempt_id)
            if attempt.reserve_usd is not None:
                totals.unresolved_reserve_usd += attempt.reserve_usd
            continue
        totals.attempts_with_usage += 1
        totals.known_lower_bound += usage.request_total
        totals.input_tokens += usage.input_tokens
        totals.output_tokens += usage.output_tokens
        totals.cached_tokens += usage.cached_tokens
        totals.cache_write_tokens += usage.cache_write_tokens
        totals.reasoning_tokens += usage.reasoning_tokens
        totals.ordinary_input += usage.ordinary_input
        totals.non_reasoning_output += usage.non_reasoning_output
        if attempt.cost_usd is not None:
            totals.known_cost_usd += attempt.cost_usd
    if totals.usage_complete:
        totals.exact_total = totals.known_lower_bound
        totals.estimated_cost_usd = totals.known_cost_usd
    else:
        totals.exact_total = None
        totals.estimated_cost_usd = None
        for name in ("input_tokens", "output_tokens", "cached_tokens", "cache_write_tokens", "reasoning_tokens",
                     "ordinary_input", "non_reasoning_output"):
            setattr(totals, name, None)
    return totals


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
