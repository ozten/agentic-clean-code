"""Per-trial workspace builder (design R03, R04, R19-R24, R32, R33).

Layout of one trial directory:

  <trial>/workspace/README.md         common brief, payment semantics, tools, submission rules
  <trial>/workspace/app/              that arm's neutral source package + fixtures
  <trial>/workspace/incident/         report.md, stdout.txt, stderr.txt, exit-code.txt, ledger.db, traces/
  <trial>/workspace/scratch/          the only agent-writable location
  <trial>/vault/                      hidden: fault-bearing ledger, evaluator result, reproduction state
  <trial>/workspace-manifest.json     exactly what the agent could read, with hashes (R24)

The agent addresses everything as /workspace/...; the harness maps that prefix to the real
directory and normalizes real paths back in every output.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import stat
import time
from pathlib import Path

from .apps import ARMS, EXCLUDED_NAME_PATTERNS, FIXTURE_FILES, FIXTURE_SOURCE, Arm
from .cases import CASES, INCIDENT_NOW, PAYMENT, Case
from .env import REPO_ROOT
from .fixtures import neutralize
from .history import HistoryProfile, cached_history
from .incident import run_incident

TASK_PROMPT = REPO_ROOT / "benchmarks" / "troubleshooting" / "task.md"
BRIEF_TEMPLATE = REPO_ROOT / "benchmarks" / "troubleshooting" / "workspace-brief.md"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_app_package(workspace: Path, arm: Arm) -> Path:
    app_dir = workspace / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    (app_dir / "fixtures").mkdir(parents=True)
    for name in arm.files:
        if any(pattern in name for pattern in EXCLUDED_NAME_PATTERNS):
            raise ValueError(f"{name} violates the inclusion policy")
        shutil.copyfile(arm.source_dir / name, app_dir / name)
    for name in FIXTURE_FILES:
        # Packaged copies carry a neutral provenance note, identically in every arm (owner decision 2026-09-06).
        fixture = neutralize(json.loads((FIXTURE_SOURCE / name).read_text()))
        (app_dir / "fixtures" / name).write_text(json.dumps(fixture, indent=2) + "\n")
    return app_dir


def operator_command(arm: Arm) -> str:
    """The invocation shown in the incident report. The provider transport configuration is
    part of the deployment environment and is deliberately not shown (R22)."""
    parts = ["python3", "-B", f"app/{arm.entry}", "--db", "incident/ledger.db",
             "--payment-id", PAYMENT["payment_id"], "--destination", PAYMENT["destination"],
             "--cents", str(PAYMENT["cents"]), "--now", str(INCIDENT_NOW)]
    if arm.records_traces:
        parts += ["--traces", "incident/traces"]
    return " ".join(parts)


def incident_report(arm: Arm, exit_code: int | None) -> str:
    traces_line = ("- `incident/traces/`: everything the application recorded at its boundaries during this run.\n"
                   if arm.records_traces else "")
    return f"""# Incident report

An operator released an approved $500 contractor payment (payment `{PAYMENT['payment_id']}`,
destination `{PAYMENT['destination']}`, {PAYMENT['cents']} cents) against the platform ledger
`incident/ledger.db`. The application reported a failure and exited with status {exit_code}.

The operator's command, run from the workspace root:

```
{operator_command(arm)}
```

The provider transport was configured by the deployment environment; that configuration is
not included here. Use the `reproduce_incident` tool to run the same invocation again under
the same environment. Each reproduction starts from the ledger exactly as it was immediately
before the operator's command and writes its own output directory under `incident/reproductions/`.

Artifacts captured from the failed run:

- `incident/stdout.txt`, `incident/stderr.txt`, `incident/exit-code.txt`: ordinary process output.
- `incident/ledger.db`: the application's SQLite ledger as it was left after the failure.
{traces_line}
The application source is under `app/`. Its provider fixtures library is `app/fixtures/`.
"""


def workspace_brief(arm: Arm) -> str:
    task = TASK_PROMPT.read_text().strip()
    template = BRIEF_TEMPLATE.read_text()
    return template.replace("{{TASK}}", task).replace("{{ENTRY}}", f"app/{arm.entry}")


def write_manifest(trial_dir: Path, workspace: Path, arm: Arm, case: Case, extra: dict | None = None) -> dict:
    files = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(workspace))] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
    manifest = {"arm": arm.id, "case": case.id, "case_version": case.version, "case_digest": case.digest(),
                "built_at": time.time(), "files": files,
                "inclusion_policy": "production modules + entry point + shared fixtures; no README/demo/tests/faults",
                "path_normalization": {"workspace": "/workspace", "python_prefix": "/python"}}
    if extra:
        manifest.update(extra)
    (trial_dir / "workspace-manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def make_read_only(path: Path) -> None:
    for item in path.rglob("*"):
        mode = item.stat().st_mode
        item.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def build_trial_workspace(trial_dir: Path, arm_id: str, case_id: str, history: HistoryProfile | None = None,
                          cache_root: Path | None = None) -> dict:
    """Build workspace + vault for one trial; returns the workspace manifest."""
    arm = ARMS[arm_id]
    case = CASES[case_id]
    history = history or HistoryProfile()
    trial_dir = trial_dir.resolve()
    workspace = trial_dir / "workspace"
    vault = trial_dir / "vault"
    if workspace.exists():
        shutil.rmtree(workspace)
    if vault.exists():
        shutil.rmtree(vault)
    workspace.mkdir(parents=True)
    (workspace / "scratch").mkdir()
    build_app_package(workspace, arm)
    traces_dir = workspace / "incident" / "traces" if arm.records_traces else None
    history_result = cached_history(cache_root, arm, history, case.precursor, workspace, vault, traces_dir)
    result = run_incident(arm, case, workspace, vault, workspace / "incident", pre_incident_db=vault / "pre-incident.db")
    ok, problems = result.matches(case, arm_id)
    if not ok:
        raise RuntimeError(f"incident generation for {arm_id}/{case_id} did not match the frozen case: {problems}")
    (workspace / "incident" / "report.md").write_text(incident_report(arm, result.exit_code))
    (workspace / "README.md").write_text(workspace_brief(arm))
    (vault / "evaluator-result.json").write_text(json.dumps({
        "arm": arm.id, "case": case.id, "before": result.before, "after": result.after, "delta": result.delta,
        "exit_code": result.exit_code, "evaluator_summary": case.evaluator_summary,
        "external_outcome": case.external_outcome, "history": {"payments": history_result.payments,
        "runs": history_result.runs, "trace_count": history_result.trace_count}}, indent=2))
    (vault / "case.json").write_text(json.dumps({"id": case.id, "slug": case.slug, "outcome": case.outcome}))
    manifest = write_manifest(trial_dir, workspace, arm, case, extra={
        "history": {**history.__dict__, "digest": history.digest(), "payments_generated": history_result.payments},
        "incident_traces": result.trace_count, "total_traces": result.total_traces})
    return manifest


def build_all_packages(output: Path | None = None, history_payments: int = 20) -> Path:
    root = (output or (REPO_ROOT / "runs" / "packages" / str(int(time.time())))).resolve()
    for case_id in CASES:
        for arm_id in ARMS:
            build_trial_workspace(root / f"{case_id}-{arm_id}", arm_id, case_id, HistoryProfile(payments=history_payments),
                                  root / "history-cache")
    return root
