"""The three arms and the inclusion rules for their neutral source packages (design R19-R22).

Inclusion policy, identical across arms:
  * production modules and the command-line entry point;
  * the shared provider fixture library (success and timeout) under app/fixtures;
  * nothing that narrates an incident: READMEs, demo scripts, tests, the fault adapter
    module, the comparison generator, evaluator outputs, design documents.
Tests are excluded from every arm because the clean app's test module reproduces the S2
mechanism verbatim; the simple app ships no tests, so exclusion keeps the arms symmetric.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .env import REPO_ROOT

EXAMPLES = REPO_ROOT / "examples"
FIXTURE_SOURCE = EXAMPLES / "contractor-payment" / "fixtures"
FIXTURE_FILES = ("success.json", "timeout.json")


@dataclass(frozen=True)
class Arm:
    id: str
    source_dir: Path
    files: tuple[str, ...]
    entry: str
    records_traces: bool
    description: str = field(default="", compare=False)

    def entry_command(self, python: str = "python3") -> list[str]:
        return [python, "-B", f"app/{self.entry}"]


ARMS: dict[str, Arm] = {
    "simple": Arm("simple", EXAMPLES / "contractor-payment-simple", ("app.py",), "app.py", False,
                  "Direct Python workflow with SQLite and request handling together."),
    "clean": Arm("clean", EXAMPLES / "contractor-payment", ("core.py", "adapters.py", "tracing.py", "main.py"),
                 "main.py", True, "Core interfaces, injected adapters, HTTP and ledger recorders."),
    "clean-no-traces": Arm("clean-no-traces", EXAMPLES / "contractor-payment",
                           ("core.py", "adapters.py", "tracing.py", "main.py"), "main.py", False,
                           "Identical clean implementation with recorders omitted at wiring."),
}

EXCLUDED_NAME_PATTERNS = ("README", "demo", "test_", "faults", "compare", "evaluator", "__pycache__")


def app_arguments(payment: dict, now: int, db: str, fixture: str | None, traces: str | None) -> list[str]:
    args = ["--db", db, "--payment-id", payment["payment_id"], "--destination", payment["destination"],
            "--cents", str(payment["cents"]), "--now", str(now)]
    if fixture:
        args += ["--fixture", fixture]
    if traces:
        args += ["--traces", traces]
    return args
