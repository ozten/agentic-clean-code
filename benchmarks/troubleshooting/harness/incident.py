"""Generate and reproduce incidents under a hidden environment (design R14, R21-R23, R27-R31).

The application is run from the *workspace copy* of its source so tracebacks show the paths
the agent sees. The ledger the app writes lives in the vault; a sanitized export (tables and
rows only, no triggers) is what the workspace receives. Fault injection, the provider fixture
selected for the incident, and any pre-incident history are host-side and never present in
agent-readable files.

Every incident run starts from the immutable pre-incident snapshot (`vault/pre-incident.db`,
produced by `history.py`, possibly with zero history). Expected results are expressed as the
balance delta the run causes plus the incident payment's row, so history rows do not matter.

Path normalization policy (R02/R23), applied identically to every arm and every tool output:
  <workspace absolute path>  -> /workspace
  <python installation prefix> -> /python
No traceback frames are removed: the application is a subprocess, so every frame is an
application or standard-library frame. Trace timestamps written during the incident run are
set to the simulated incident clock (INCIDENT_NOW), as for history records.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .apps import ARMS, Arm, app_arguments
from .cases import CASES, INCIDENT_NOW, INITIAL_CENTS, PAYMENT, Case
from .env import REPO_ROOT
from .fixtures import make_fixture, write_fixture
from .isolation import Sandbox, python_for_sandbox

INCIDENT_TRANSFER_ID = "tr_demo_500"


def path_normalizer(workspace: Path):
    replacements = [(str(workspace.resolve()), "/workspace"), (str(workspace), "/workspace"),
                    (str(Path(sys.base_prefix).resolve()), "/python"), (str(Path(sys.base_prefix)), "/python")]
    replacements.sort(key=lambda pair: -len(pair[0]))

    def normalize(text: str) -> str:
        for real, neutral in replacements:
            text = text.replace(real, neutral)
        return text
    return normalize


def initialize_database(arm: Arm, path: Path, initial_cents: int = INITIAL_CENTS) -> None:
    """Create the arm's own schema and initial funds using that arm's code (host side)."""
    if arm.id == "simple":
        spec = importlib.util.spec_from_file_location("simple_payment_app", arm.source_dir / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.initialize(path, initial_cents)
    else:
        source = str(arm.source_dir)
        if source not in sys.path:
            sys.path.insert(0, source)
        from adapters import SqliteLedger  # type: ignore

        ledger = SqliteLedger(path)
        ledger.seed(initial_cents)
        ledger.close()


def apply_fault(case: Case, database: Path) -> None:
    if case.fault.kind == "none":
        return
    if case.fault.kind != "sqlite_trigger":
        raise ValueError(f"unsupported fault kind {case.fault.kind}")
    with sqlite3.connect(database) as db:
        db.executescript(case.fault.sql)


def incident_fixture(vault: Path, case: Case, happy: bool = False) -> Path:
    """The provider outcome wired for the incident run lives in the vault, never in app/fixtures."""
    outcome = "success" if happy else case.outcome
    return write_fixture(vault / f"incident-fixture-{outcome}.json",
                         make_fixture(PAYMENT["payment_id"], PAYMENT["destination"], PAYMENT["cents"], outcome,
                                      INCIDENT_TRANSFER_ID))


def export_sanitized_database(source: Path, destination: Path) -> None:
    """Copy application tables, indexes, and rows into a fresh file. Triggers and views never copy."""
    if destination.exists():
        destination.unlink()
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        rows = src.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid").fetchall()
        for kind, name, sql in rows:
            if kind == "table":
                dst.execute(sql)
        for kind, name, sql in rows:
            if kind == "table":
                data = src.execute(f'SELECT * FROM "{name}"').fetchall()
                if data:
                    placeholders = ",".join("?" * len(data[0]))
                    dst.executemany(f'INSERT INTO "{name}" VALUES ({placeholders})', data)
        for kind, name, sql in rows:
            if kind == "index":
                dst.execute(sql)
        dst.commit()
    finally:
        src.close()
        dst.close()


def snapshot_state(database: Path, payment_id: str = PAYMENT["payment_id"]) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        available, reserved, contractor = db.execute(
            "SELECT available, reserved, contractor FROM balances").fetchone()
        postings, = db.execute("SELECT count(*) FROM postings").fetchone()
        payment_rows, = db.execute("SELECT count(*) FROM payments").fetchone()
        row = db.execute("SELECT transfer_id, created_at FROM payments WHERE id = ?", (payment_id,)).fetchone()
        posting = db.execute("SELECT count(*) FROM postings WHERE payment_id = ?", (payment_id,)).fetchone()[0] > 0
    return {"balances": {"available": available, "reserved": reserved, "contractor": contractor},
            "payment_rows": payment_rows, "postings": postings,
            "incident": {"row": row is not None, "transfer_id": row[0] if row else None,
                         "created_at": row[1] if row else None, "posting": posting}}


def balance_delta(before: dict, after: dict) -> dict:
    return {key: after["balances"][key] - before["balances"][key] for key in ("available", "reserved", "contractor")}


def schema_text(database: Path) -> list[str]:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        return [sql for sql, in db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]


def rewrite_new_trace_times(traces_dir: Path | None, known: set[Path], simulated_time: int) -> int:
    if not traces_dir or not traces_dir.exists():
        return 0
    new = sorted(set(traces_dir.glob("trace-*/trace.json")) - known)
    for offset, path in enumerate(new):
        record = json.loads(path.read_text())
        record["metadata"]["started_at_unix"] = simulated_time + offset
        path.write_text(json.dumps(record, indent=2) + "\n")
    return len(new)


@dataclass
class IncidentResult:
    arm: str
    case: str
    exit_code: int | None
    stdout: str
    stderr: str
    before: dict
    after: dict
    delta: dict
    trace_count: int                 # records written by this run
    total_traces: int                # records in the evidence trace directory afterwards
    error_line: str | None
    timed_out: bool
    elapsed_seconds: float
    fixture_outcome: str
    notes: list[str] = field(default_factory=list)

    def matches(self, case: Case, arm_id: str | None = None) -> tuple[bool, list[str]]:
        arm_id = arm_id or self.arm
        problems = []
        if self.delta != case.expected_delta:
            problems.append(f"balance delta {self.delta} != expected {case.expected_delta}")
        incident = {k: self.after["incident"][k] for k in ("row", "transfer_id", "posting")}
        if incident != case.expected_incident:
            problems.append(f"incident row {incident} != expected {case.expected_incident}")
        if self.exit_code != case.expected_exit:
            problems.append(f"exit {self.exit_code} != expected {case.expected_exit}")
        expected_error = case.error_for(arm_id)
        if expected_error and expected_error not in self.stderr:
            problems.append(f"expected error text {expected_error!r} missing from stderr")
        if expected_error and "Traceback (most recent call last)" not in self.stderr:
            problems.append("traceback missing from stderr")
        return not problems, problems


def run_incident(arm: Arm, case: Case, workspace: Path, vault_dir: Path, evidence_dir: Path, *,
                 pre_incident_db: Path | None = None, happy: bool = False) -> IncidentResult:
    """Run the incident (or a happy path) hidden-side from the pre-incident snapshot; write sanitized evidence."""
    workspace, vault_dir, evidence_dir = workspace.resolve(), vault_dir.resolve(), evidence_dir.resolve()
    vault_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    database = vault_dir / "ledger.db"
    if database.exists():
        database.unlink()
    if pre_incident_db is None:
        pre_incident_db = vault_dir / "pre-incident.db"
        if not pre_incident_db.exists():
            initialize_database(arm, pre_incident_db)
    shutil.copyfile(pre_incident_db, database)
    before = snapshot_state(database)
    if not happy:
        apply_fault(case, database)
    fixture = incident_fixture(vault_dir, case, happy)
    traces_dir = evidence_dir / "traces" if arm.records_traces else None
    known = set(traces_dir.glob("trace-*/trace.json")) if traces_dir and traces_dir.exists() else set()
    python = python_for_sandbox()
    argv = arm.entry_command(python) + app_arguments(PAYMENT, INCIDENT_NOW, str(database), str(fixture),
                                                     str(traces_dir) if traces_dir else None)
    sandbox = Sandbox(workspace, writable=(vault_dir, evidence_dir), home=vault_dir / "home")
    (vault_dir / "home").mkdir(exist_ok=True)
    result = sandbox.run(argv, timeout=60)
    normalize = path_normalizer(workspace)
    stdout, stderr = normalize(result.stdout), normalize(result.stderr)
    (evidence_dir / "stdout.txt").write_text(stdout)
    (evidence_dir / "stderr.txt").write_text(stderr)
    (evidence_dir / "exit-code.txt").write_text(f"{result.returncode}\n")
    export_sanitized_database(database, evidence_dir / "ledger.db")
    after = snapshot_state(database)
    new_traces = rewrite_new_trace_times(traces_dir, known, INCIDENT_NOW)
    total = len(list(traces_dir.glob("trace-*/trace.json"))) if traces_dir else 0
    error_line = next((line for line in stderr.splitlines() if line.startswith("Payment ") and "failed" in line), None)
    return IncidentResult(arm.id, case.id, result.returncode, stdout, stderr, before, after,
                          balance_delta(before, after), new_traces, total, error_line, result.timed_out,
                          result.elapsed_seconds, "success" if happy else case.outcome)


def check_parity(output: Path | None = None, history_payments: int = 6) -> dict:
    """P1 acceptance: every arm produces the same delta, incident row, exit, and schema for happy and S1-S5,
    with each arm's own expected error wording present and a full traceback."""
    from .history import HistoryProfile, cached_history
    from .packaging import build_app_package

    root = (output or (REPO_ROOT / "runs" / "parity" / str(int(time.time())))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    profile = HistoryProfile(payments=history_payments)
    report: dict = {"root": str(root), "cases": {}, "parity": True, "problems": [], "history_payments": history_payments}
    for case_id, case in [("happy", CASES["S2"]), *CASES.items()]:
        results, schemas = {}, {}
        happy = case_id == "happy"
        for arm_id, arm in ARMS.items():
            trial = root / case_id / arm_id
            workspace, vault = trial / "workspace", trial / "vault"
            build_app_package(workspace, arm)
            (workspace / "scratch").mkdir(exist_ok=True)
            traces_dir = workspace / "incident" / "traces" if arm.records_traces else None
            cached_history(root / "history-cache", arm, profile, None if happy else case.precursor, workspace, vault, traces_dir)
            result = run_incident(arm, case, workspace, vault, workspace / "incident", pre_incident_db=vault / "pre-incident.db", happy=happy)
            results[arm_id] = result
            schemas[arm_id] = schema_text(vault / "ledger.db")
            if not happy:
                ok, problems = result.matches(case, arm_id)
                if not ok:
                    report["parity"] = False
                    report["problems"] += [f"{case_id}/{arm_id}: {p}" for p in problems]
            elif result.delta != {"available": -50_000, "reserved": 0, "contractor": 50_000} or result.exit_code != 0:
                report["parity"] = False
                report["problems"].append(f"happy/{arm_id}: delta {result.delta} exit {result.exit_code}")
        if len({json.dumps(r.delta, sort_keys=True) for r in results.values()}) != 1:
            report["parity"] = False
            report["problems"].append(f"{case_id}: balance delta differs across arms")
        if len({json.dumps(r.after['incident'], sort_keys=True) for r in results.values()}) != 1:
            report["parity"] = False
            report["problems"].append(f"{case_id}: incident row differs across arms")
        if len({json.dumps(s) for s in schemas.values()}) != 1:
            report["parity"] = False
            report["problems"].append(f"{case_id}: schema differs across arms")
        report["cases"][case_id] = {arm: {"exit": r.exit_code, "delta": r.delta, "incident": r.after["incident"],
                                          "traces": r.trace_count, "total_traces": r.total_traces, "error": r.error_line,
                                          "has_traceback": "Traceback" in r.stderr, "payment_rows": r.after["payment_rows"]}
                                    for arm, r in results.items()}
        for arm_id, r in results.items():
            (root / case_id / arm_id / "vault" / "evaluator-result.json").write_text(json.dumps(asdict(r), indent=2))
    return report
