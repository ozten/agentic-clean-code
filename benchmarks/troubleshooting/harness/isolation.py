"""Kernel-enforced per-trial isolation using macOS Seatbelt (``sandbox-exec``) (design R19-R26).

Every tool subprocess a trial runs, and every application run for incident generation or
reproduction, executes under a profile that:
  * denies everything by default;
  * allows reads of the system, the pinned Python installation, and the trial workspace;
  * allows writes only to the paths explicitly listed (scratch, a reproduction output dir);
  * denies all networking (DNS included) and process listing;
  * receives a minimal environment with no inherited variables (no API key, no HOME).
The vault directory holding fault injection, evaluator results, and prior-trial artifacts
sits outside the workspace subtree and is therefore unreadable.

Docker is not available on this machine; Seatbelt provides the process/filesystem boundary
the design asks for. The adversarial checks in ``run_leak_checks`` prove the boundary rather
than assuming it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .env import sandbox_environment

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
DEFAULT_TIMEOUT = 60.0

PROFILE_TEMPLATE = """(version 1)
(deny default)
(allow process-exec)
(allow process-fork)
(allow signal (target self))
(allow sysctl-read (sysctl-name-prefix "hw.") (sysctl-name-prefix "kern.os") (sysctl-name "kern.version")
     (sysctl-name "kern.hostname") (sysctl-name "kern.argmax") (sysctl-name "kern.boottime")
     (sysctl-name "kern.usrstack64") (sysctl-name "kern.proc.pid.self") (sysctl-name-prefix "kern.proc.pid.")
     (sysctl-name "kern.maxfilesperproc") (sysctl-name "kern.secure_kernel") (sysctl-name-prefix "machdep.")
     (sysctl-name-prefix "vm.") (sysctl-name-prefix "net.inet.tcp.") (sysctl-name "kern.tcsm_available")
     (sysctl-name "kern.tcsm_enable"))
(allow mach-lookup (global-name "com.apple.system.logger") (global-name "com.apple.system.notification_center"))
(allow file-read-metadata)
(allow file-read* (literal "/") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/System")
     (subpath "/Library/Preferences") (subpath "/private/etc") (subpath "/dev") (subpath "/private/var/db/timezone")
     (subpath "/opt/homebrew") (subpath "/usr/local"))
(allow file-read* (subpath "%(workspace)s"))
%(writable_rules)s
(allow file-write* (literal "/dev/null") (literal "/dev/tty") (regex #"^/dev/fd/"))
(allow file-ioctl (subpath "/dev"))
"""


def python_for_sandbox() -> str:
    """The base interpreter, never the harness virtualenv (which holds the OpenAI SDK)."""
    base = Path(sys.base_prefix)
    for candidate in (base / "bin" / "python3.12", base / "bin" / "python3"):
        if candidate.exists():
            return str(candidate.resolve())
    return sys.executable


@dataclass
class SandboxResult:
    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_seconds: float
    raw_stdout_bytes: int = 0
    raw_stderr_bytes: int = 0


@dataclass
class Sandbox:
    workspace: Path
    writable: tuple[Path, ...] = ()
    home: Path | None = None
    profile_path: Path | None = None
    extra_env: dict[str, str] = field(default_factory=dict)

    def profile(self) -> str:
        rules = "\n".join(f'(allow file-read* file-write* (subpath "{p.resolve()}"))' for p in self.writable)
        return PROFILE_TEMPLATE % {"workspace": self.workspace.resolve(), "writable_rules": rules}

    def environment(self) -> dict[str, str]:
        env = sandbox_environment(self.home or (self.workspace / "scratch"))
        # `python3` must resolve to the pinned interpreter, not Apple's Xcode stub in /usr/bin.
        env["PATH"] = str(Path(python_for_sandbox()).parent) + ":" + env["PATH"]
        env.update(self.extra_env)
        return env

    def run(self, argv: list[str], timeout: float = DEFAULT_TIMEOUT, cwd: Path | None = None,
            stdin: str | None = None, max_capture: int | None = None) -> SandboxResult:
        if not os.path.exists(SANDBOX_EXEC):
            raise RuntimeError("sandbox-exec is required for isolated execution and was not found")
        profile = self.profile_path
        if profile is None:
            profile = (self.workspace.parent / "sandbox.sb").resolve()
            profile.write_text(self.profile())
        full = [SANDBOX_EXEC, "-f", str(Path(profile).resolve()), *argv]
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(full, cwd=str(cwd or self.workspace), env=self.environment(),
                                       input=stdin, capture_output=True, timeout=timeout)
            out, err, rc = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            out, err, rc = exc.stdout or b"", exc.stderr or b"", None
        elapsed = time.monotonic() - started
        raw_out, raw_err = len(out), len(err)
        if max_capture is not None:
            out, err = out[:max_capture], err[:max_capture]
        return SandboxResult(argv, rc, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"),
                             timed_out, elapsed, raw_out, raw_err)


# ---------------------------------------------------------------------------------------
# Adversarial leak checks (R26)
# ---------------------------------------------------------------------------------------

FORBIDDEN_MARKERS = (
    "hidden_confirmation_fault", "hidden_preparation_fault", "fail_confirmation", "CREATE TRIGGER",
    "evaluator", "evaluator-result", "evaluator_summary", "preparation-failure", "confirmation-failure",
    "response-lost", "vault", "compare.py", "DiskFullOnConfirmation", "agent-troubleshooting-measurements",
    "OPEN_AI_API_KEY", "sk-", "benchmark-artifacts", "best-architecture", "bad-code",
)


def leak_probe_commands(trial_dir: Path, workspace: Path, repo_root: Path, home: str) -> list[tuple[str, list[str]]]:
    """Attempts an adversarial agent might make. Each must fail or reveal nothing forbidden."""
    py = python_for_sandbox()
    vault = trial_dir / "vault"
    return [
        ("list parent of workspace", ["/bin/ls", "-la", str(trial_dir)]),
        ("list grandparent (other trials)", ["/bin/ls", "-la", str(trial_dir.parent)]),
        ("read vault evaluator result", ["/bin/cat", str(vault / "evaluator-result.json")]),
        ("read vault ledger with trigger", [py, "-B", "-c",
            f"import sqlite3; print(sqlite3.connect('file:{vault / 'ledger.db'}?mode=ro', uri=True)"
            ".execute('select sql from sqlite_master').fetchall())"]),
        ("triggers in supplied incident database", [py, "-B", "-c",
            "import sqlite3; db=sqlite3.connect('file:incident/ledger.db?mode=ro', uri=True); "
            "print(db.execute(\"select type,name,sql from sqlite_master\").fetchall())"]),
        ("raw bytes of incident database", [py, "-B", "-c", "import re; data=open('incident/ledger.db','rb').read(); print(sorted(set(re.findall(rb'[A-Za-z_]{6,}', data)))[:80])"]),
        ("grep workspace for markers", ["/usr/bin/grep", "-rIl", "-e", "TRIGGER", "-e", "evaluator", "-e", "vault", "."]),
        ("process list", ["/bin/ps", "-axo", "pid,command"]),
        ("sysctl process args", ["/usr/sbin/sysctl", "-a"]),
        ("read repository design doc", ["/bin/cat", str(repo_root / "docs/plans/2026-09-06-agent-troubleshooting-measurements.md")]),
        ("read repository .env", ["/bin/cat", str(repo_root / ".env")]),
        ("list repository", ["/bin/ls", str(repo_root)]),
        ("read real home", ["/bin/ls", home]),
        ("environment dump", ["/usr/bin/env"]),
        ("python environ", [py, "-B", "-c", "import os,sys; print(sorted(os.environ)); print(sys.path)"]),
        ("network to provider", ["/usr/bin/curl", "-sS", "-m", "3", "https://api.stripe.com/v1/transfers"]),
        ("network to inference host", ["/usr/bin/curl", "-sS", "-m", "3", "https://api.openai.com/v1/models"]),
        ("dns lookup", [py, "-B", "-c", "import socket; print(socket.gethostbyname('api.openai.com'))"]),
        ("write into app source", ["/bin/sh", "-c", "echo x > app/injected.txt && echo WROTE"]),
        ("write into incident evidence", ["/bin/sh", "-c", "echo x > incident/injected.txt && echo WROTE"]),
        ("symlink escape", ["/bin/sh", "-c", f"ln -s {trial_dir} scratch/escape && cat scratch/escape/vault/evaluator-result.json"]),
        ("proc self via lsof", ["/usr/sbin/lsof", "-p", "1"]),
        ("read previous trial artifact", ["/bin/cat", str(trial_dir.parent / "previous-trial" / "workspace" / "incident" / "stderr.txt")]),
    ]


def run_leak_checks(output: Path | None = None, verbose: bool = False) -> dict:
    """Build a fresh S2 clean workspace next to a decoy previous trial, then attack it."""
    from .env import REPO_ROOT
    from .packaging import build_trial_workspace

    root = (output or (REPO_ROOT / "runs" / "leak-check" / str(int(time.time())))).resolve()
    root.mkdir(parents=True, exist_ok=True)
    decoy = root / "previous-trial" / "workspace" / "incident"
    decoy.mkdir(parents=True, exist_ok=True)
    (decoy / "stderr.txt").write_text("PREVIOUS TRIAL evaluator-result leak canary\n")
    results = []
    all_passed = True
    for arm_id in ("clean", "simple"):
        trial_dir = root / f"probe-{arm_id}"
        build_trial_workspace(trial_dir, arm_id, "S2")
        workspace = trial_dir / "workspace"
        sandbox = Sandbox(workspace, writable=(workspace / "scratch",))
        home = os.path.expanduser("~")
        for label, argv in leak_probe_commands(trial_dir, workspace, REPO_ROOT, home):
            result = sandbox.run(argv, timeout=20)
            combined = result.stdout + result.stderr
            leaked = [m for m in FORBIDDEN_MARKERS if m in combined and not _benign(m, label, combined)]
            wrote = "WROTE" in result.stdout
            passed = not leaked and not wrote and "leak canary" not in combined
            all_passed &= passed
            results.append({"arm": arm_id, "probe": label, "returncode": result.returncode, "passed": passed,
                            "leaked_markers": leaked, "stdout_head": result.stdout[:200],
                            "stderr_head": result.stderr[:200]})
            if verbose:
                print(f"[{'ok' if passed else 'LEAK'}] {arm_id:6} {label}: rc={result.returncode} {result.stderr.strip()[:80] or result.stdout.strip()[:80]}")
    summary = {"probes": len(results), "failed": [r for r in results if not r["passed"]], "root": str(root)}
    return {"passed": all_passed, "summary": summary, "results": results}


def _benign(marker: str, label: str, text: str) -> bool:
    # Error messages echo the attempted path, e.g. "cat: /.../vault/evaluator-result.json: Operation not
    # permitted". That is the sandbox refusing, not a disclosure of content. Treat a marker as benign
    # only when every line containing it is a permission-denied/not-found line.
    lines = [line for line in text.splitlines() if marker in line]
    return bool(lines) and all(("Operation not permitted" in line or "No such file" in line
                                or "Permission denied" in line or "PermissionError" in line
                                or "unable to open database" in line) for line in lines)


def clean_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
