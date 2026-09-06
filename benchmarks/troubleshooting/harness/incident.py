"""Generate and reproduce incidents under a hidden environment (design R14, R21-R23, R27-R31).

The application is run from the *workspace copy* of its source so tracebacks show the paths
the agent sees. The ledger the app writes lives in the vault; a sanitized export (tables and
rows only, no triggers) is what the workspace receives. Fault injection happens host-side,
before the application starts, and is never present in agent-readable files.

Path normalization policy (R02/R23), applied identically to every arm and every tool output:
  <workspace absolute path>  -> /workspace
  <python installation prefix> -> /python
No traceback frames are removed: the application is a subprocess, so every frame is an
application or standard-library frame.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .apps import ARMS, Arm, app_arguments
from .cases import CASES, INCIDENT_NOW, INITIAL_CENTS, PAYMENT, Case
from .env import REPO_ROOT
from .isolation import Sandbox, python_for_sandbox


def path_normalizer(workspace: Path):
    replacements = [(str(workspace.resolve()), "/workspace"), (str(workspace), "/workspace"),
                    (str(Path(sys.base_prefix).resolve()), "/python"), (str(Path(sys.base_prefix)), "/python")]
    replacements.sort(key=lambda pair: -len(pair[0]))

    def normalize(text: str) -> str:
        for real, neutral in replacements:
            text = text.replace(real, neutral)
        return text
    return normalize


def initialize_database(arm: Arm, path: Path) -> None:
    """Create the arm's own schema and initial funds using that arm's code (host side)."""
    if arm.id == "simple":
        spec = importlib.util.spec_from_file_location("simple_payment_app", arm.source_dir / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.initialize(path, INITIAL_CENTS)
    else:
        source = str(arm.source_dir)
        if source not in sys.path:
            sys.path.insert(0, source)
        from adapters import SqliteLedger  # type: ignore

        ledger = SqliteLedger(path)
        ledger.seed(INITIAL_CENTS)
        ledger.close()


def apply_fault(case: Case, database: Path) -> None:
    if case.fault.kind == "none":
        return
    if case.fault.kind != "sqlite_trigger":
        raise ValueError(f"unsupported fault kind {case.fault.kind}")
    with sqlite3.connect(database) as db:
        db.executescript(case.fault.sql)


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


def snapshot_state(database: Path) -> dict:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        available, reserved, contractor = db.execute(
            "SELECT available, reserved, contractor FROM balances").fetchone()
        postings, = db.execute("SELECT count(*) FROM postings").fetchone()
        payment_rows, = db.execute("SELECT count(*) FROM payments").fetchone()
        row = db.execute("SELECT transfer_id FROM payments").fetchone()
    return {"available": available, "reserved": reserved, "contractor": contractor, "postings": postings,
            "transfer_id": row[0] if row else None, "payment_rows": payment_rows}


def schema_text(database: Path) -> list[str]:
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        return [sql for sql, in db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name")]


@dataclass
class IncidentResult:
    arm: str
    case: str
    exit_code: int | None
    stdout: str
    stderr: str
    state: dict
    trace_count: int
    error_line: str | None
    timed_out: bool
    elapsed_seconds: float
    fixture_consumed: bool

    def matches(self, case: Case) -> tuple[bool, list[str]]:
        problems = []
        if self.state != case.expected_state:
            problems.append(f"state {self.state} != expected {case.expected_state}")
        if self.exit_code != case.expected_exit:
            problems.append(f"exit {self.exit_code} != expected {case.expected_exit}")
        if case.expected_error and case.expected_error not in self.stderr:
            problems.append(f"expected error text {case.expected_error!r} missing from stderr")
        if case.expected_error and "Traceback (most recent call last)" not in self.stderr:
            problems.append("traceback missing from stderr")
        return not problems, problems


def run_incident(arm: Arm, case: Case, workspace: Path, vault_dir: Path, evidence_dir: Path,
                 *, happy: bool = False) -> IncidentResult:
    """Run the incident (or a happy path) hidden-side and write sanitized evidence to evidence_dir."""
    workspace = workspace.resolve()
    vault_dir = vault_dir.resolve()
    evidence_dir = evidence_dir.resolve()
    vault_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    database = vault_dir / "ledger.db"
    if database.exists():
        database.unlink()
    initialize_database(arm, database)
    fixture = "success.json" if happy else case.fixture
    if not happy:
        apply_fault(case, database)
    traces_dir = evidence_dir / "traces" if arm.records_traces else None
    if traces_dir and traces_dir.exists():
        shutil.rmtree(traces_dir)
    python = python_for_sandbox()
    argv = arm.entry_command(python) + app_arguments(
        PAYMENT, INCIDENT_NOW, str(database), f"app/fixtures/{fixture}",
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
    state = snapshot_state(database)
    trace_count = len(list(traces_dir.glob("trace-*/trace.json"))) if traces_dir else 0
    error_line = next((line for line in stderr.splitlines() if line.startswith("Payment ") and "failed" in line), None)
    fixture_consumed = case.provider_calls > 0 if not happy else True
    return IncidentResult(arm.id, case.id, result.returncode, stdout, stderr, state, trace_count, error_line,
                          result.timed_out, result.elapsed_seconds, fixture_consumed)


def check_parity(output: Path | None = None) -> dict:
    """P1 acceptance: every arm produces the same state, exit, error text, and schema for S1-S3 and happy."""
    from .packaging import build_app_package

    root = (output or (REPO_ROOT / "runs" / "parity" / str(int(time.time())))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report: dict = {"root": str(root), "cases": {}, "parity": True, "problems": []}
    for case_id, case in [("happy", CASES["S2"]), *CASES.items()]:
        results = {}
        schemas = {}
        for arm_id, arm in ARMS.items():
            trial = root / case_id / arm_id
            workspace = trial / "workspace"
            build_app_package(workspace, arm)
            (workspace / "scratch").mkdir(exist_ok=True)
            result = run_incident(arm, case, workspace, trial / "vault", workspace / "incident", happy=(case_id == "happy"))
            results[arm_id] = result
            schemas[arm_id] = schema_text(trial / "vault" / "ledger.db") if case_id == "happy" else None
            if case_id != "happy":
                ok, problems = result.matches(case)
                if not ok:
                    report["parity"] = False
                    report["problems"] += [f"{case_id}/{arm_id}: {p}" for p in problems]
        states = {arm: r.state for arm, r in results.items()}
        if len({json.dumps(s, sort_keys=True) for s in states.values()}) != 1:
            report["parity"] = False
            report["problems"].append(f"{case_id}: state differs across arms {states}")
        if case_id == "happy" and len({json.dumps(s) for s in schemas.values()}) != 1:
            report["parity"] = False
            report["problems"].append("schema differs across arms")
        errors = {arm: r.error_line for arm, r in results.items()}
        if len(set(errors.values())) != 1:
            report["parity"] = False
            report["problems"].append(f"{case_id}: error line differs across arms {errors}")
        report["cases"][case_id] = {arm: {"exit": r.exit_code, "state": r.state, "traces": r.trace_count,
                                          "error": r.error_line, "has_traceback": "Traceback" in r.stderr}
                                    for arm, r in results.items()}
        for arm_id, r in results.items():
            (root / case_id / arm_id / "vault" / "evaluator-result.json").write_text(json.dumps(asdict(r), indent=2))
    return report
