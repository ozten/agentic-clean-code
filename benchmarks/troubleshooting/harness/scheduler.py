"""Manifest freezing, block randomization, execution, resume, replacement (design R16-R18, R58, R59, P4).

Run directory layout:
  runs/<run_id>/manifest.json   frozen copy of the manifest plus computed hashes/versions
  runs/<run_id>/plan.json       ordered trials with ids, blocks, and arm order
  runs/<run_id>/state.json      per-trial status: pending | in_progress | completed | needs_review | replaced
  runs/<run_id>/budget.json     spend gate
  runs/<run_id>/trials/<id>/    workspace, vault, ledgers, responses, summary, grade

Resume: completed trials are never re-run; a trial left `in_progress` by a crash is marked
`needs_review` (its ledger may hold an unanswered `sent` row) and is not resent (V11).
Replacements get new ids and link to the original, which keeps its records (R37).
"""
from __future__ import annotations

import hashlib
import json
import platform
import random
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .accounting import PricingProfile, load_pricing
from .apps import ARMS
from .budget import BudgetGate
from .cases import CASES, case_manifest
from .env import REPO_ROOT, load_settings
from .inference import FIXED_REQUEST_SETTINGS, ModelSettings
from .ledger import now_iso
from .loop import Limits, TrialContext, TrialRunner
from .history import HistoryProfile
from .packaging import BRIEF_TEMPLATE, TASK_PROMPT, build_trial_workspace
from .tools import TOOL_SCHEMAS

HARNESS_DIR = Path(__file__).resolve().parent
INSTRUCTIONS_PATH = HARNESS_DIR.parent / "instructions.md"


def harness_source_hash() -> str:
    digest = hashlib.sha256()
    for path in sorted(HARNESS_DIR.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def sdk_version() -> str:
    import openai

    return openai.__version__


def load_manifest(path: Path) -> dict:
    manifest = json.loads(Path(path).read_text())
    required = ("experiment_version", "phase", "models", "arms", "cases", "repetitions", "scheduler_seed",
                "batch_usd_cap", "pricing_snapshot")
    missing = [key for key in required if key not in manifest]
    if missing:
        raise ValueError(f"manifest is missing required keys: {missing}")
    if Decimal(str(manifest["batch_usd_cap"])) <= 0:
        raise ValueError("batch_usd_cap must be a positive dollar amount")
    for role, spec in manifest["models"].items():
        if not spec.get("id"):
            raise ValueError(f"model role {role} has no id; there is no runtime default model (OA07)")
    for arm in manifest["arms"]:
        if arm not in ARMS:
            raise ValueError(f"unknown arm {arm}")
    for case in manifest["cases"]:
        if case not in CASES:
            raise ValueError(f"unknown case {case}")
    return manifest


def limits_from(manifest: dict) -> Limits:
    return Limits(**{**Limits().as_dict(), **manifest.get("limits", {})})


def history_from(manifest: dict) -> HistoryProfile:
    return HistoryProfile(**manifest.get("history", {}))


def build_plan(manifest: dict) -> list[dict]:
    """Blocks of (model, case, repetition) with arm order shuffled by the recorded seed (R18)."""
    rng = random.Random(int(manifest["scheduler_seed"]))
    blocks = []
    for role, spec in manifest["models"].items():
        for case in manifest["cases"]:
            for repetition in range(1, int(manifest["repetitions"]) + 1):
                arms = list(manifest["arms"])
                rng.shuffle(arms)
                blocks.append({"block_id": f"{role}-{case}-r{repetition}", "model_role": role, "model": spec["id"],
                               "case": case, "repetition": repetition, "arm_order": arms})
    rng.shuffle(blocks)
    trials = []
    order = 0
    for block in blocks:
        for arm in block["arm_order"]:
            order += 1
            trials.append({"order": order, "trial_id": str(uuid.uuid4()), "block_id": block["block_id"],
                           "model_role": block["model_role"], "model": block["model"], "case": block["case"],
                           "repetition": block["repetition"], "arm": arm, "replaces": None})
    return trials


def instructions_text() -> str:
    return INSTRUCTIONS_PATH.read_text()


def plan_run(manifest_path: Path, run_id: str | None = None, runs_dir: Path | None = None) -> Path:
    manifest = load_manifest(manifest_path)
    settings = load_settings()
    if settings.max_usd_cap is not None and Decimal(str(manifest["batch_usd_cap"])) > settings.max_usd_cap:
        raise ValueError(f"manifest batch_usd_cap exceeds HARNESS_MAX_USD_CAP={settings.max_usd_cap}")
    runs_dir = runs_dir or settings.runs_dir
    run_id = run_id or f"{manifest['phase']}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = (runs_dir / run_id).resolve()
    if run_dir.exists():
        raise FileExistsError(f"run {run_dir} already exists; resume it or choose another id")
    run_dir.mkdir(parents=True)
    pricing_path = (REPO_ROOT / "benchmarks" / "troubleshooting" / manifest["pricing_snapshot"]).resolve()
    shutil.copyfile(pricing_path, run_dir / "pricing-snapshot.json")
    frozen = {
        **manifest, "run_id": run_id, "frozen_at": now_iso(), "manifest_source": str(manifest_path),
        "harness_source_sha256": harness_source_hash(), "openai_sdk_version": sdk_version(),
        "python_version": sys.version, "platform": platform.platform(), "machine": platform.machine(),
        "sandbox": "macOS Seatbelt (sandbox-exec), deny-default profile per trial",
        "cases_frozen": case_manifest(), "fixed_request_settings": FIXED_REQUEST_SETTINGS,
        "history_profile": {**history_from(manifest).__dict__, "digest": history_from(manifest).digest()},
        "reasoning_effort": manifest.get("reasoning_effort", "medium"),
        "tool_schema_sha256": hashlib.sha256(json.dumps(TOOL_SCHEMAS, sort_keys=True).encode()).hexdigest(),
        "instructions_sha256": hashlib.sha256(instructions_text().encode()).hexdigest(),
        "task_prompt_sha256": hashlib.sha256(TASK_PROMPT.read_bytes()).hexdigest(),
        "workspace_brief_sha256": hashlib.sha256(BRIEF_TEMPLATE.read_bytes()).hexdigest(),
        "pricing_snapshot_sha256": hashlib.sha256(pricing_path.read_bytes()).hexdigest(),
        "openai_project_id": settings.openai_project_id, "concurrency": 1,
        "text_only_policy": "one reminder to call submit_diagnosis, then a second text-only turn ends the trial as submitted_text",
        "manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
    }
    (run_dir / "manifest.json").write_text(json.dumps(frozen, indent=2, default=str))
    trials = build_plan(manifest)
    (run_dir / "plan.json").write_text(json.dumps({"trials": trials}, indent=2))
    (run_dir / "state.json").write_text(json.dumps({"trials": {t["trial_id"]: {"status": "pending"} for t in trials},
                                                    "paused": None}, indent=2))
    BudgetGate(run_dir, Decimal(str(manifest["batch_usd_cap"])))
    return run_dir


def load_state(run_dir: Path) -> dict:
    return json.loads((run_dir / "state.json").read_text())


def save_state(run_dir: Path, state: dict) -> None:
    temporary = run_dir / "state.tmp"
    temporary.write_text(json.dumps(state, indent=2))
    temporary.replace(run_dir / "state.json")


def load_plan(run_dir: Path) -> list[dict]:
    return json.loads((run_dir / "plan.json").read_text())["trials"]


def save_plan(run_dir: Path, trials: list[dict]) -> None:
    (run_dir / "plan.json").write_text(json.dumps({"trials": trials}, indent=2))


def profile_for(frozen: dict, run_dir: Path, model_role: str, dry_run: bool) -> PricingProfile:
    if dry_run:
        from .fake import DRY_RUN_PROFILE

        return DRY_RUN_PROFILE
    profiles = load_pricing(run_dir / "pricing-snapshot.json")
    key = frozen["models"][model_role].get("pricing_profile") or frozen["models"][model_role]["id"]
    if key not in profiles:
        raise ValueError(f"no pricing profile {key} in the frozen snapshot; the model cannot enter a dollar comparison")
    return profiles[key]


def model_settings_for(frozen: dict, model_role: str, dry_run: bool) -> ModelSettings:
    spec = frozen["models"][model_role]
    if dry_run:
        from .fake import FAKE_MODEL

        return ModelSettings(FAKE_MODEL, frozen.get("reasoning_effort", "medium"))
    return ModelSettings(spec["id"], frozen.get("reasoning_effort", "medium"), spec.get("reasoning_context"),
                         frozen.get("include_encrypted_reasoning", True), spec.get("reasoning_summary"))


def make_client(frozen: dict, dry_run: bool, per_call_timeout: float):
    if dry_run:
        from .fake import ScriptedClient

        return ScriptedClient()
    from .inference import ResponsesClient

    settings = load_settings()
    if not settings.key_present:
        raise RuntimeError("OPEN_AI_API_KEY is absent; preflight must pass before paid work")
    return ResponsesClient(settings.openai_api_key, settings.openai_project_id, per_call_timeout)


def run_one_trial(run_dir: Path, frozen: dict, trial: dict, client, budget: BudgetGate, dry_run: bool) -> dict:
    trial_dir = run_dir / "trials" / trial["trial_id"]
    trial_dir.mkdir(parents=True, exist_ok=True)
    (trial_dir / "trial.json").write_text(json.dumps({**trial, "started_at": now_iso(), "dry_run": dry_run}, indent=2))
    build_trial_workspace(trial_dir, trial["arm"], trial["case"], history_from(frozen), run_dir / "history-cache")
    limits = limits_from(frozen)
    settings = load_settings()
    ctx = TrialContext(
        trial_id=trial["trial_id"], trial_dir=trial_dir, workspace=trial_dir / "workspace", vault=trial_dir / "vault",
        arm=trial["arm"], case=trial["case"], model_settings=model_settings_for(frozen, trial["model_role"], dry_run),
        profile=profile_for(frozen, run_dir, trial["model_role"], dry_run), limits=limits,
        instructions=instructions_text(), initial_input=(trial_dir / "workspace" / "README.md").read_text(),
        secrets=[settings.openai_api_key])
    if hasattr(client, "reset"):
        client.reset()
    runner = TrialRunner(ctx, client, budget)
    summary = runner.run()
    return summary


def execute_run(manifest_path: Path | None, run_dir: Path | None = None, dry_run: bool = False,
                max_trials: int | None = None) -> dict:
    if run_dir is None:
        if manifest_path is None:
            raise ValueError("either --manifest or --run is required")
        run_dir = plan_run(manifest_path)
    run_dir = Path(run_dir).resolve()
    frozen = json.loads((run_dir / "manifest.json").read_text())
    if not dry_run:
        from .preflight import format_report, run_preflight

        result = run_preflight()
        print(format_report(result))
        if not result.ok:
            return {"ok": False, "run_dir": str(run_dir), "escalate": result.kind, "message": result.escalation_message()}
    budget = BudgetGate(run_dir)
    plan = load_plan(run_dir)
    state = load_state(run_dir)
    executed = 0
    outcome = {"ok": True, "run_dir": str(run_dir), "executed": [], "skipped_completed": 0, "needs_review": [],
               "paused": None}
    # Crash recovery (V11): anything left in_progress is never resent.
    for trial in plan:
        entry = state["trials"].setdefault(trial["trial_id"], {"status": "pending"})
        if entry["status"] == "in_progress":
            entry["status"] = "needs_review"
            entry["note"] = "found in_progress on resume; ledger may contain an unanswered sent row; not resent"
            outcome["needs_review"].append(trial["trial_id"])
    save_state(run_dir, state)
    if state.get("paused"):
        outcome["ok"] = False
        outcome["paused"] = state["paused"]
        return outcome
    client = make_client(frozen, dry_run, limits_from(frozen).per_call_timeout)
    for trial in plan:
        entry = state["trials"][trial["trial_id"]]
        if entry["status"] in ("completed", "needs_review", "replaced"):
            outcome["skipped_completed"] += entry["status"] == "completed"
            continue
        if budget.cancelled:
            outcome["ok"] = False
            outcome["paused"] = "cancelled"
            break
        if max_trials is not None and executed >= max_trials:
            break
        entry.update(status="in_progress", started_at=now_iso())
        save_state(run_dir, state)
        try:
            summary = run_one_trial(run_dir, frozen, trial, client, budget, dry_run)
        except Exception as exc:  # noqa: BLE001
            entry.update(status="needs_review", note=f"harness exception: {type(exc).__name__}: {exc}", finished_at=now_iso())
            save_state(run_dir, state)
            state["paused"] = {"reason": f"harness exception in trial {trial['trial_id']}: {exc}", "at": now_iso()}
            save_state(run_dir, state)
            outcome["ok"] = False
            outcome["paused"] = state["paused"]
            break
        executed += 1
        entry.update(status="completed", finished_at=now_iso(), stop_reason=summary["stop_reason"],
                     exact_total_tokens=summary["exact_total_tokens"], telemetry_complete=summary["telemetry_complete"])
        save_state(run_dir, state)
        outcome["executed"].append({"trial_id": trial["trial_id"], "arm": trial["arm"], "case": trial["case"],
                                    "model": trial["model"], "stop_reason": summary["stop_reason"],
                                    "tokens": summary["exact_total_tokens"], "cost": summary["estimated_cost_usd"]})
        if summary.get("pause_batch"):
            state["paused"] = {"reason": f"trial {trial['trial_id']} requested a pause: {summary['stop_detail']}",
                               "at": now_iso()}
            save_state(run_dir, state)
            outcome["ok"] = False
            outcome["paused"] = state["paused"]
            break
    outcome["budget"] = budget.summary()
    outcome["remaining"] = sum(1 for t in plan if state["trials"][t["trial_id"]]["status"] == "pending")
    return outcome


def run_status(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    state = load_state(run_dir)
    plan = load_plan(run_dir)
    counts: dict[str, int] = {}
    for trial in plan:
        status = state["trials"].get(trial["trial_id"], {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    return {"run_dir": str(run_dir), "trials": len(plan), "by_status": counts, "paused": state.get("paused"),
            "budget": BudgetGate(run_dir).summary()}


def cancel_run(run_dir: Path, reason: str) -> str:
    gate = BudgetGate(Path(run_dir).resolve())
    gate.cancel(reason)
    return f"cancelled: {reason}"


def unpause_run(run_dir: Path, note: str) -> None:
    run_dir = Path(run_dir).resolve()
    state = load_state(run_dir)
    state.setdefault("pause_history", []).append({**(state.get("paused") or {}), "cleared_at": now_iso(), "note": note})
    state["paused"] = None
    save_state(run_dir, state)


def replace_trial(run_dir: Path, trial_id: str, reason: str) -> dict:
    """Schedule a replacement under the infrastructure-failure policy; the original keeps its records."""
    run_dir = Path(run_dir).resolve()
    plan = load_plan(run_dir)
    state = load_state(run_dir)
    original = next(t for t in plan if t["trial_id"] == trial_id)
    replacement = {**original, "trial_id": str(uuid.uuid4()), "order": max(t["order"] for t in plan) + 1,
                   "replaces": trial_id, "replacement_reason": reason}
    plan.append(replacement)
    state["trials"][trial_id]["status"] = "replaced"
    state["trials"][trial_id]["replaced_by"] = replacement["trial_id"]
    state["trials"][replacement["trial_id"]] = {"status": "pending"}
    save_plan(run_dir, plan)
    save_state(run_dir, state)
    return replacement


def estimate_spend(manifest_path: Path, expected_tokens_per_trial: int = 40_000, expected_output_share: float = 0.10,
                   qualification_usd: Decimal = Decimal("0.50")) -> dict:
    """Expected and worst-case rate-card spend for a manifest. Worst case charges the whole
    100k-token trial cap at the higher of the output and max-input rates for every trial."""
    manifest = load_manifest(manifest_path)
    profiles = load_pricing(REPO_ROOT / "benchmarks" / "troubleshooting" / manifest["pricing_snapshot"])
    limits = limits_from(manifest)
    trials_per_model = len(manifest["arms"]) * len(manifest["cases"]) * int(manifest["repetitions"])
    lines = {}
    expected_total = Decimal("0")
    worst_total = Decimal("0")
    for role, spec in manifest["models"].items():
        profile = profiles[spec.get("pricing_profile") or spec["id"]]
        expected_output = int(expected_tokens_per_trial * expected_output_share)
        expected_input = expected_tokens_per_trial - expected_output
        expected_per_trial = (Decimal(expected_input) * profile.ordinary_input + Decimal(expected_output) * profile.output) / Decimal(1_000_000)
        worst_per_trial = Decimal(limits.token_cap) * max(profile.output, profile.max_input_rate) / Decimal(1_000_000)
        lines[role] = {"model": spec["id"], "trials": trials_per_model,
                       "expected_usd_per_trial": str(expected_per_trial), "expected_usd": str(expected_per_trial * trials_per_model),
                       "worst_case_usd_per_trial": str(worst_per_trial), "worst_case_usd": str(worst_per_trial * trials_per_model)}
        expected_total += expected_per_trial * trials_per_model
        worst_total += worst_per_trial * trials_per_model
    return {"trials": trials_per_model * len(manifest["models"]), "assumptions": {
                "expected_tokens_per_trial": expected_tokens_per_trial, "expected_output_share": expected_output_share,
                "worst_case": f"{limits.token_cap} tokens per trial at the higher of output and max-input rates",
                "input_token_counting": "assumed free; unverified on the pricing page", "qualification_usd": str(qualification_usd)},
            "by_model": lines, "expected_usd": str(expected_total + qualification_usd),
            "worst_case_usd": str(worst_total + qualification_usd), "batch_usd_cap": str(manifest["batch_usd_cap"]),
            "cap_covers_worst_case": Decimal(str(manifest["batch_usd_cap"])) >= worst_total + qualification_usd}
