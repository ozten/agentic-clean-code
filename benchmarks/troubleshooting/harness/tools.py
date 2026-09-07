"""Function tools offered to the model (design OA02, R25, R27-R29, R42).

Every filesystem/shell tool executes inside the trial sandbox; `reproduce_incident` runs
host-side because it must apply the hidden environment. Outputs are capped at 16 KiB with
explicit truncation metadata; the untruncated text is kept in tool-outputs/ (R42). Real
paths are normalized to /workspace in everything the model sees.
"""
from __future__ import annotations

import json
import shlex
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .apps import ARMS, app_arguments
from .cases import CASES, INCIDENT_NOW, PAYMENT
from .incident import (apply_fault, export_sanitized_database, incident_fixture, path_normalizer,
                       rewrite_new_trace_times, snapshot_state)
from .isolation import Sandbox, python_for_sandbox

TOOL_OUTPUT_CAP = 16 * 1024
SHELL_TIMEOUT = 60

SUBMISSION_FIELDS = ("failed_boundary", "evidence", "external_outcome", "local_state", "reproduction", "recovery")

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "name": "list_files", "strict": True,
     "description": "List files under a workspace path (recursively, up to a depth) with sizes in bytes.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"path": {"type": "string", "description": "Directory relative to /workspace, e.g. 'app' or '/workspace/incident'."},
                                   "max_depth": {"type": ["integer", "null"], "description": "Maximum depth (default 3)."}},
                    "required": ["path", "max_depth"]}},
    {"type": "function", "name": "read_file", "strict": True,
     "description": "Read a text file from the workspace with line numbers. Use start_line to continue a truncated read.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"path": {"type": "string"},
                                   "start_line": {"type": ["integer", "null"], "description": "1-based first line (default 1)."},
                                   "max_lines": {"type": ["integer", "null"], "description": "Maximum lines to return (default all)."}},
                    "required": ["path", "start_line", "max_lines"]}},
    {"type": "function", "name": "search_text", "strict": True,
     "description": "Search files under a workspace path for a pattern (grep -rn). Returns matching lines with file paths.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"pattern": {"type": "string"},
                                   "path": {"type": "string", "description": "File or directory relative to /workspace (default '.')."},
                                   "regex": {"type": ["boolean", "null"], "description": "Interpret pattern as an extended regex (default false: fixed string)."}},
                    "required": ["pattern", "path", "regex"]}},
    {"type": "function", "name": "run_shell", "strict": True,
     "description": "Run a shell command from the workspace root in an isolated environment (no network; writes only under scratch/). Python 3 and sqlite3 are available.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {"command": {"type": "string"},
                                   "timeout_seconds": {"type": ["integer", "null"], "description": "Up to 60 (default 60)."}},
                    "required": ["command", "timeout_seconds"]}},
    {"type": "function", "name": "reproduce_incident", "strict": True,
     "description": "Rerun the operator's exact invocation under the original environment, starting from a freshly funded ledger. Returns process output, exit status, and the new output directory under incident/reproductions/.",
     "parameters": {"type": "object", "additionalProperties": False, "properties": {}, "required": []}},
    {"type": "function", "name": "submit_diagnosis", "strict": True,
     "description": "Submit the final diagnosis. The trial ends immediately after this call.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "properties": {
                        "failed_boundary": {"type": "string", "description": "Which operation/component failed and where in the payment flow."},
                        "evidence": {"type": "string", "description": "Citations: file paths, line numbers, database rows, recorded artifacts."},
                        "external_outcome": {"type": "string", "description": "What is known and unknown about the provider's state."},
                        "local_state": {"type": "string", "description": "The ledger state the incident left behind."},
                        "reproduction": {"type": "string", "description": "Deterministic reproduction procedure and regression-test assertions."},
                        "recovery": {"type": "string", "description": "Safe next action preserving payment identity and reserved funds."}},
                    "required": list(SUBMISSION_FIELDS)}},
]

LIST_FILES_CODE = r"""
import os, sys
root, depth = sys.argv[1], int(sys.argv[2])
root = root.rstrip('/') or '.'
if not os.path.exists(root):
    print(f"not found: {root}"); sys.exit(1)
if os.path.isfile(root):
    print(f"{os.path.getsize(root):>9}  {root}"); sys.exit(0)
for current, dirs, files in os.walk(root):
    rel = os.path.relpath(current, root)
    level = 0 if rel == '.' else rel.count(os.sep) + 1
    if level >= depth:
        dirs[:] = []
    dirs.sort(); files.sort()
    for name in files:
        path = os.path.join(current, name)
        try: size = os.path.getsize(path)
        except OSError: size = -1
        print(f"{size:>9}  {path}")
    for name in dirs:
        print(f"{'<dir>':>9}  {os.path.join(current, name)}/")
"""

READ_FILE_CODE = r"""
import sys
path, start, count = sys.argv[1], int(sys.argv[2]), sys.argv[3]
count = None if count == 'all' else int(count)
try:
    data = open(path, 'rb').read()
except IsADirectoryError:
    print(f"{path} is a directory"); sys.exit(1)
except FileNotFoundError:
    print(f"not found: {path}"); sys.exit(1)
if b'\0' in data[:4096]:
    print(f"{path} is a binary file ({len(data)} bytes); use run_shell with sqlite3 or python to inspect it"); sys.exit(0)
lines = data.decode('utf-8', 'replace').splitlines()
end = len(lines) if count is None else min(len(lines), start - 1 + count)
for number in range(max(1, start), end + 1):
    print(f"{number:5}| {lines[number - 1]}")
if end < len(lines):
    print(f"[{len(lines) - end} more lines; continue with start_line={end + 1}]")
"""


def _text(value) -> str:
    return value if isinstance(value, str) else json.dumps(value)


@dataclass
class ToolResult:
    output: str                 # what the model receives (possibly truncated)
    raw_output: str             # untruncated
    truncated: bool
    exit_code: int | None
    elapsed_seconds: float
    kind: str                   # action taxonomy hint
    extra: dict


class ToolExecutor:
    def __init__(self, trial_dir: Path, workspace: Path, vault: Path, arm_id: str, case_id: str,
                 output_cap: int = TOOL_OUTPUT_CAP):
        self.trial_dir = trial_dir.resolve()
        self.workspace = workspace.resolve()
        self.vault = vault.resolve()
        self.arm = ARMS[arm_id] if arm_id else None
        self.case = CASES[case_id] if case_id else None
        self.output_cap = output_cap
        self.sandbox = Sandbox(self.workspace, writable=(self.workspace / "scratch",))
        self.normalize = path_normalizer(self.workspace)
        self.python = python_for_sandbox()
        self.reproductions = 0

    # -- path handling ------------------------------------------------------------------
    def resolve(self, path: str) -> str:
        """Map /workspace/... or relative paths onto the real workspace; sandbox enforces containment."""
        text = (path or ".").strip()
        if text.startswith("/workspace"):
            text = text[len("/workspace"):].lstrip("/") or "."
        return text

    def rewrite_command(self, command: str) -> str:
        return command.replace("/workspace/", str(self.workspace) + "/").replace("/workspace", str(self.workspace))

    # -- dispatch -----------------------------------------------------------------------
    def execute(self, name: str, arguments: dict) -> ToolResult:
        started = time.monotonic()
        handler = {"list_files": self.list_files, "read_file": self.read_file, "search_text": self.search_text,
                   "run_shell": self.run_shell, "reproduce_incident": self.reproduce_incident}.get(name)
        if handler is None:
            raw = f"unknown tool {name}"
            return ToolResult(raw, raw, False, None, time.monotonic() - started, "other", {})
        try:
            result = handler(**arguments)
        except TypeError as exc:
            raw = f"invalid arguments for {name}: {exc}"
            return ToolResult(raw, raw, False, None, time.monotonic() - started, "other", {})
        result.elapsed_seconds = time.monotonic() - started
        return result

    def _finish(self, raw: str, exit_code: int | None, kind: str, extra: dict | None = None) -> ToolResult:
        raw = self.normalize(raw)
        encoded = raw.encode()
        truncated = len(encoded) > self.output_cap
        shown = raw
        if truncated:
            shown = encoded[:self.output_cap].decode("utf-8", "ignore")
            shown += (f"\n[output truncated: showing {self.output_cap} of {len(encoded)} bytes; "
                      "use read_file with start_line, or narrower commands, to see more]")
        return ToolResult(shown, raw, truncated, exit_code, 0.0, kind, extra or {})

    # -- tools --------------------------------------------------------------------------
    def list_files(self, path: str, max_depth=None) -> ToolResult:
        depth = 3 if max_depth is None else max(1, int(max_depth))
        result = self.sandbox.run([self.python, "-B", "-c", LIST_FILES_CODE, self.resolve(path), str(depth)], timeout=30)
        return self._finish(result.stdout + result.stderr, result.returncode, "discover_files")

    def read_file(self, path: str, start_line=None, max_lines=None) -> ToolResult:
        start = 1 if start_line is None else max(1, int(start_line))
        count = "all" if max_lines is None else str(max(1, int(max_lines)))
        target = self.resolve(path)
        result = self.sandbox.run([self.python, "-B", "-c", READ_FILE_CODE, target, str(start), count], timeout=30)
        kind = "read_incident_evidence" if target.startswith("incident") else "read_source"
        return self._finish(result.stdout + result.stderr, result.returncode, kind, {"path": target})

    def search_text(self, pattern: str, path: str, regex=None) -> ToolResult:
        flag = "-E" if regex else "-F"
        target = self.resolve(path or ".")
        result = self.sandbox.run(["/usr/bin/grep", "-rnI", flag, "--", pattern, target], timeout=30)
        out = result.stdout + result.stderr
        if result.returncode == 1 and not out.strip():
            out = "(no matches)"
        return self._finish(out, result.returncode, "search_text", {"pattern": pattern, "path": target})

    def run_shell(self, command: str, timeout_seconds=None) -> ToolResult:
        timeout = SHELL_TIMEOUT if timeout_seconds is None else max(1, min(SHELL_TIMEOUT, int(timeout_seconds)))
        rewritten = self.rewrite_command(command)
        result = self.sandbox.run(["/bin/sh", "-c", rewritten], timeout=timeout)
        out = result.stdout
        if result.stderr:
            out += ("\n" if out and not out.endswith("\n") else "") + "[stderr]\n" + result.stderr
        if result.timed_out:
            out += f"\n[command timed out after {timeout} seconds]"
        out += f"\n[exit status {result.returncode}]" if result.returncode is not None else ""
        return self._finish(out, result.returncode, classify_shell(command), {"command": command,
                                                                            "timed_out": result.timed_out})

    def reproduce_incident(self) -> ToolResult:
        """Fresh incident reproduction (R27-R29): reset state, apply the hidden environment, run, sanitize.

        A recovery continuation (running the app again against the post-incident ledger) is
        something the agent can do itself with run_shell against a copy under scratch/; this
        tool always reproduces the original incident from the freshly funded ledger.
        """
        if self.arm is None or self.case is None:
            return self._finish("reproduce_incident is not available in this workspace", 1, "other")
        self.reproductions += 1
        number = self.reproductions
        out_dir = self.workspace / "incident" / "reproductions" / f"{number:02d}"
        hidden = self.vault / "reproductions" / f"{number:02d}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        hidden.mkdir(parents=True, exist_ok=True)
        database = hidden / "ledger.db"
        if database.exists():
            database.unlink()
        shutil.copyfile(self.vault / "pre-incident.db", database)     # immutable snapshot (R29)
        apply_fault(self.case, database)
        fixture = incident_fixture(self.vault, self.case)
        traces_dir = out_dir / "traces" if self.arm.records_traces else None
        argv = self.arm.entry_command(self.python) + app_arguments(
            PAYMENT, INCIDENT_NOW, str(database), str(fixture), str(traces_dir) if traces_dir else None)
        sandbox = Sandbox(self.workspace, writable=(hidden, out_dir), home=hidden, readable=(self.vault / fixture.name,))
        result = sandbox.run(argv, timeout=60)
        rewrite_new_trace_times(traces_dir, set(), INCIDENT_NOW)
        stdout, stderr = self.normalize(result.stdout), self.normalize(result.stderr)
        (out_dir / "stdout.txt").write_text(stdout)
        (out_dir / "stderr.txt").write_text(stderr)
        (out_dir / "exit-code.txt").write_text(f"{result.returncode}\n")
        export_sanitized_database(database, out_dir / "ledger.db")
        state = snapshot_state(database)
        rel = f"incident/reproductions/{number:02d}"
        files = sorted(str(p.relative_to(self.workspace)) for p in out_dir.rglob("*") if p.is_file())
        text = (f"Reproduction {number}: exit status {result.returncode}\n"
                f"Output directory: /workspace/{rel}\nFiles: {', '.join(files)}\n"
                f"--- stdout ---\n{stdout}--- stderr ---\n{stderr}")
        return self._finish(text, result.returncode, "reproduce", {"reproduction": number, "state": state,
                                                                  "output_dir": rel})


def classify_shell(command: str) -> str:
    """Coarse action taxonomy for a shell command (R45). Compound commands are 'mixed'."""
    lowered = command.strip().lower()
    if any(sep in lowered for sep in ("&&", "||", ";", "|")):
        return "mixed"
    head = shlex.split(lowered)[0] if lowered else ""
    head = head.rsplit("/", 1)[-1]
    if head in ("ls", "find", "tree", "du"):
        return "discover_files"
    if head in ("grep", "rg", "ag", "ack"):
        return "search_text"
    if head in ("cat", "head", "tail", "less", "more", "sed", "awk", "wc", "nl"):
        return "read_incident_evidence" if "incident" in lowered else "read_source"
    if head in ("sqlite3",) or ("sqlite3" in lowered and "python" in head):
        return "query_local_state"
    if head.startswith("python"):
        if "unittest" in lowered or "pytest" in lowered or "app/" in lowered:
            return "reproduce_or_test"
        if "sqlite" in lowered:
            return "query_local_state"
        if "grep" in lowered or "re." in lowered or "search" in lowered:
            return "search_text"
        return "other"
    return "other"
