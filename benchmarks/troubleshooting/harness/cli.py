"""Command-line entry points. Paid work needs an explicit manifest; tests never call the API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_preflight(args) -> int:
    from .preflight import format_report, run_preflight

    result = run_preflight(Path(args.env) if args.env else None, record=not args.no_record)
    print(format_report(result))
    return result.exit_code


def cmd_parity(args) -> int:
    from .incident import check_parity

    report = check_parity(Path(args.output) if args.output else None)
    print(json.dumps(report, indent=2))
    return 0 if report["parity"] else 1


def cmd_build_packages(args) -> int:
    from .packaging import build_all_packages

    root = build_all_packages(Path(args.output) if args.output else None)
    print(f"Packages written under {root}")
    return 0


def cmd_leak_check(args) -> int:
    from .isolation import run_leak_checks

    report = run_leak_checks(Path(args.output) if args.output else None, verbose=True)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["passed"] else 1


def cmd_plan(args) -> int:
    from .scheduler import plan_run

    run_dir = plan_run(Path(args.manifest), run_id=args.run_id)
    print(f"Run planned at {run_dir}")
    return 0


def cmd_estimate(args) -> int:
    from .scheduler import estimate_spend

    print(json.dumps(estimate_spend(Path(args.manifest)), indent=2, default=str))
    return 0


def cmd_run(args) -> int:
    from .scheduler import execute_run

    outcome = execute_run(Path(args.manifest) if args.manifest else None,
                          run_dir=Path(args.run) if args.run else None,
                          dry_run=args.dry_run, max_trials=args.max_trials)
    print(json.dumps(outcome, indent=2, default=str))
    return 0 if outcome.get("ok") else 1


def cmd_status(args) -> int:
    from .scheduler import run_status

    print(json.dumps(run_status(Path(args.run)), indent=2, default=str))
    return 0


def cmd_cancel(args) -> int:
    from .scheduler import cancel_run

    print(cancel_run(Path(args.run), reason=args.reason))
    return 0


def cmd_qualify(args) -> int:
    from .qualify import run_qualification

    outcome = run_qualification(Path(args.manifest), dry_run=args.dry_run)
    print(json.dumps(outcome, indent=2, default=str))
    return 0 if outcome.get("ok") else 1


def cmd_grade(args) -> int:
    from .grading import grade_run

    print(json.dumps(grade_run(Path(args.run), trial_id=args.trial), indent=2, default=str))
    return 0


def cmd_analyze(args) -> int:
    from .analysis import analyze_run

    report = analyze_run(Path(args.run))
    print(report["markdown"])
    return 0


def cmd_review(args) -> int:
    from .grading import record_human_review

    print(json.dumps(record_human_review(Path(args.run), args.trial, args.correct,
                                         args.notes or "", reviewer=args.reviewer), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="validate the OpenAI key with GET /v1/models; no completions")
    p.add_argument("--env", help="alternate .env path (tests only)")
    p.add_argument("--no-record", action="store_true")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("parity", help="run S1-S3 across all arms and compare application state")
    p.add_argument("--output")
    p.set_defaults(func=cmd_parity)

    p = sub.add_parser("build-packages", help="build neutral per-arm/case workspaces for inspection")
    p.add_argument("--output")
    p.set_defaults(func=cmd_build_packages)

    p = sub.add_parser("leak-check", help="adversarial isolation checks against built workspaces")
    p.add_argument("--output")
    p.set_defaults(func=cmd_leak_check)

    p = sub.add_parser("plan", help="freeze a run directory from a manifest")
    p.add_argument("--manifest", required=True)
    p.add_argument("--run-id")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("estimate", help="expected and worst-case spend for a manifest")
    p.add_argument("--manifest", required=True)
    p.set_defaults(func=cmd_estimate)

    p = sub.add_parser("run", help="execute (or resume) a run; --dry-run uses a scripted fake model")
    p.add_argument("--manifest")
    p.add_argument("--run")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-trials", type=int)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("cancel", help="stop scheduling new inference for a run")
    p.add_argument("--run", required=True)
    p.add_argument("--reason", default="operator cancel")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("qualify", help="harness qualification exercise (paid unless --dry-run)")
    p.add_argument("--manifest", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_qualify)

    p = sub.add_parser("grade", help="machine-grade submissions in a run")
    p.add_argument("--run", required=True)
    p.add_argument("--trial")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("review", help="record a human review verdict for a trial")
    p.add_argument("--run", required=True)
    p.add_argument("--trial", required=True)
    p.add_argument("--correct", required=True, choices=["yes", "no"])
    p.add_argument("--notes")
    p.add_argument("--reviewer", default="human")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("analyze")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_analyze)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
