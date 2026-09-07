"""Pre-incident payment history: a deterministic run of earlier payments through the application itself.

Why: pilot-v1 workspaces held one payment and, for the traces arm, three trace records, so the
incident's evidence needed no finding. Production evidence is a ledger with many rows and a trace
directory with many records. Scaling the evidence (owner decision 2026-09-06) exercises
correlation without changing either application.

How: `HistoryProfile(payments=N, seed=S)` derives N earlier payments (distinct ids, destinations,
amounts, simulated times spread over `span_seconds` before the incident). Each is executed by the
arm's own entry point in the sandbox with a per-payment fixture kept in the vault; about
`timeout_fraction` of them first time out and are then retried successfully, exactly as the apps
are designed to handle. A case's precursor (an earlier attempt of the incident payment) runs last.
Trace `started_at_unix` values are rewritten to the simulated clock so ledger `created_at` and
trace timestamps agree; this is the hidden environment's clock, applied identically to every arm.

Results are cached per (arm, profile, precursor) inside a run directory so every trial of that
combination starts from byte-identical pre-incident state.
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .apps import Arm, app_arguments
from .cases import INCIDENT_NOW, INITIAL_CENTS, PAYMENT, Precursor
from .fixtures import make_fixture, write_fixture
from .isolation import Sandbox, python_for_sandbox


@dataclass(frozen=True)
class HistoryProfile:
    payments: int = 0
    seed: int = 20260906
    timeout_fraction: float = 0.1
    span_seconds: int = 30 * 24 * 3600
    min_cents: int = 1_000
    max_cents: int = 40_000

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class HistoryPayment:
    payment_id: str
    destination: str
    cents: int
    created_at: int
    timeout_first: bool


def history_payments(profile: HistoryProfile) -> list[HistoryPayment]:
    rng = random.Random(profile.seed)
    start = INCIDENT_NOW - profile.span_seconds
    times = sorted(rng.randint(start, INCIDENT_NOW - 3600) for _ in range(profile.payments))
    payments = []
    for index, created_at in enumerate(times, start=1):
        payments.append(HistoryPayment(
            payment_id=f"inv-{rng.randint(1000, 9999)}-{index:03d}",
            destination=f"acct_{rng.choice(['north', 'harbor', 'summit', 'meadow', 'delta', 'orchard'])}_{rng.randint(10, 99)}",
            cents=rng.randint(profile.min_cents, profile.max_cents) // 100 * 100,
            created_at=created_at, timeout_first=rng.random() < profile.timeout_fraction))
    return payments


@dataclass
class HistoryResult:
    database: Path
    traces_dir: Path | None
    payments: int
    runs: int
    trace_count: int
    initial_cents: int
    elapsed_seconds: float


def _rewrite_trace_times(traces_dir: Path, known: set[Path], simulated_time: int) -> set[Path]:
    """Set started_at_unix of trace records created since `known` to the simulated clock."""
    current = set(traces_dir.glob("trace-*/trace.json")) if traces_dir else set()
    for offset, path in enumerate(sorted(current - known)):
        record = json.loads(path.read_text())
        record["metadata"]["started_at_unix"] = simulated_time + offset
        path.write_text(json.dumps(record, indent=2) + "\n")
    return current


def build_history(arm: Arm, profile: HistoryProfile, workspace: Path, vault: Path, traces_dir: Path | None,
                  precursor: Precursor | None) -> HistoryResult:
    """Produce vault/pre-incident.db (and the history part of traces_dir) by running the app."""
    started = time.monotonic()
    workspace, vault = workspace.resolve(), vault.resolve()
    database = vault / "pre-incident.db"
    if database.exists():
        database.unlink()
    fixtures_dir = vault / "history-fixtures"
    if fixtures_dir.exists():
        shutil.rmtree(fixtures_dir)
    if traces_dir:
        traces_dir = traces_dir.resolve()
        if traces_dir.exists():
            shutil.rmtree(traces_dir)
        traces_dir.mkdir(parents=True)
    payments = history_payments(profile)
    initial = INITIAL_CENTS + sum(p.cents for p in payments)
    python = python_for_sandbox()
    sandbox = Sandbox(workspace, writable=(vault, *( [traces_dir] if traces_dir else [])), home=vault / "home")
    (vault / "home").mkdir(parents=True, exist_ok=True)
    known: set[Path] = set()
    runs = 0

    def run(payment_id, destination, cents, now, outcome, expect_exit):
        nonlocal runs, known
        fixture = write_fixture(fixtures_dir / f"{payment_id}-{outcome}-{now}.json",
                                make_fixture(payment_id, destination, cents, outcome))
        argv = arm.entry_command(python) + app_arguments({"payment_id": payment_id, "destination": destination, "cents": cents},
                                                         now, str(database), str(fixture), str(traces_dir) if traces_dir else None)
        argv += ["--initial-cents", str(initial)]
        result = sandbox.run(argv, timeout=60)
        runs += 1
        if result.returncode != expect_exit:
            raise RuntimeError(f"history run for {payment_id} ({outcome}) exited {result.returncode}: {result.stderr[-400:]}")
        if traces_dir:
            known = _rewrite_trace_times(traces_dir, known, now)

    for payment in payments:
        if payment.timeout_first:
            run(payment.payment_id, payment.destination, payment.cents, payment.created_at, "timeout", 1)
            run(payment.payment_id, payment.destination, payment.cents, payment.created_at + 600, "success", 0)
        else:
            run(payment.payment_id, payment.destination, payment.cents, payment.created_at, "success", 0)
    if precursor:
        run(PAYMENT["payment_id"], PAYMENT["destination"], PAYMENT["cents"], INCIDENT_NOW - precursor.age_seconds,
            precursor.outcome, 1 if precursor.outcome == "timeout" else 0)
    if not database.exists():
        # No history at all: create the funded schema with the arm's own code.
        from .incident import initialize_database

        initialize_database(arm, database, initial)
    trace_count = len(list(traces_dir.glob("trace-*/trace.json"))) if traces_dir else 0
    return HistoryResult(database, traces_dir, len(payments), runs, trace_count, initial, time.monotonic() - started)


def cache_key(arm: Arm, profile: HistoryProfile, precursor: Precursor | None) -> str:
    return f"{arm.id}-{profile.digest()}-{'none' if precursor is None else f'{precursor.outcome}{precursor.age_seconds}'}"


def cached_history(cache_root: Path | None, arm: Arm, profile: HistoryProfile, precursor: Precursor | None,
                   workspace: Path, vault: Path, traces_dir: Path | None) -> HistoryResult:
    """Build once per (arm, profile, precursor) under cache_root, then copy into this trial's vault/workspace."""
    if cache_root is None:
        return build_history(arm, profile, workspace, vault, traces_dir, precursor)
    slot = cache_root / cache_key(arm, profile, precursor)
    meta = slot / "history.json"
    if not meta.exists():
        slot.mkdir(parents=True, exist_ok=True)
        result = build_history(arm, profile, workspace, slot / "vault", slot / "traces" if traces_dir else None, precursor)
        meta.write_text(json.dumps({"payments": result.payments, "runs": result.runs, "trace_count": result.trace_count,
                                    "initial_cents": result.initial_cents, "elapsed_seconds": result.elapsed_seconds}))
    info = json.loads(meta.read_text())
    vault.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(slot / "vault" / "pre-incident.db", vault / "pre-incident.db")
    if traces_dir:
        if traces_dir.exists():
            shutil.rmtree(traces_dir)
        shutil.copytree(slot / "traces", traces_dir)
    return HistoryResult(vault / "pre-incident.db", traces_dir, info["payments"], info["runs"], info["trace_count"],
                         info["initial_cents"], 0.0)
