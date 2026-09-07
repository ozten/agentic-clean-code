"""Six-dimension correctness grading with machine checks and a human review workflow (R48-R53).

Dimensions: failed_boundary, external_outcome, local_state, evidence, reproducibility, recovery.
Every dimension is critical: `correct` requires all six and no disqualifier. Disqualifiers
(R50): a new payment identity/idempotency key for the unresolved payment, releasing uncertain
reserved funds, claiming bank settlement, or citing a transfer id that is not in the evidence.

Machine checks are heuristic pattern matches over the submission text plus mechanical citation
existence checks against the workspace manifest. They separate facts from judgment (R52) but
are not the final authority: `grade.json` carries `machine`, `human`, and `final`; `final` is
the human verdict when present, else the machine verdict. Review packets are blinded to model,
tokens, and time (R53); the arm can still be inferred from cited file names.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cases import CASES
from .ledger import now_iso

# Narrow negation for action recommendations ("do not release", "never use a new key").
ACTION_NEGATION = r"(?:\bnot\b|\bnever\b|\bdon't\b|\bdo not\b|\bmust not\b|\bmustn't\b|\bshould not\b|\bshouldn't\b|\bwithout\b|\brather than\b|\binstead of\b|\bavoid\w*\b|\bnor\b|\bneither\b|\bno\s*$|\bno\s+new\b)"
# Broader negation for factual claims ("does not prove settlement", "settlement is unknown").
CLAIM_NEGATION = r"(?:not|no|never|cannot|can't|doesn't|does not|isn't|is not|unproven|unknown|uncertain|without|neither|nor|no evidence|not proof|rather than|unconfirmed|outside)"


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in patterns)


def _negated_near(text: str, pattern: str, window: int = 80, negation: str = CLAIM_NEGATION,
                  after_window: int = 40) -> bool:
    """True if every occurrence of `pattern` has a negation within `window` chars before it
    (or `after_window` chars after it)."""
    hits = list(re.finditer(pattern, text, re.IGNORECASE))
    if not hits:
        return True
    for hit in hits:
        before = text[max(0, hit.start() - window):hit.start()]
        after = text[hit.end():hit.end() + after_window]
        if not (re.search(negation, before, re.IGNORECASE) or (after_window and re.search(negation, after, re.IGNORECASE))):
            return False
    return True


def _negated_action(text: str, pattern: str) -> bool:
    """An action is negated only by a negation earlier in the same sentence/clause."""
    hits = list(re.finditer(pattern, text, re.IGNORECASE))
    for hit in hits:
        before = text[max(0, hit.start() - 120):hit.start()]
        before = re.split(r"[.;!?]\s", before)[-1]          # same sentence only
        if not re.search(ACTION_NEGATION, before, re.IGNORECASE):
            return False
    return True


@dataclass
class DimensionResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def extract_citations(text: str) -> list[str]:
    """Paths the submission cites: app/..., incident/..., /workspace/..., with optional :line."""
    found = re.findall(r"(?:/workspace/)?((?:app|incident|scratch)/[A-Za-z0-9_./\-]+)", text)
    cleaned = []
    for path in found:
        path = path.rstrip(".,;:)")
        path = re.sub(r":\d+(?:-\d+)?$", "", path)
        if path not in cleaned:
            cleaned.append(path)
    return cleaned


CLAIM_FIELDS = ("failed_boundary", "external_outcome", "local_state", "recovery")


def check_disqualifiers(sub: dict, case_id: str) -> list[str]:
    # The reproduction field describes a test: it may name fixture ids and assert that nothing is released.
    text = " ".join(str(sub.get(k, "")) for k in CLAIM_FIELDS)
    problems = []
    # New identity for the unresolved payment.
    new_identity = r"(?:new|fresh|different|another|regenerat\w*|rotate\w*)\s+(?:payment[\s_-]*id|payment identity|idempotency[\s_-]*key)"
    if _has(text, new_identity) and not _negated_action(text, new_identity):
        problems.append("recommends a new payment identity or idempotency key for an unresolved payment")
    # Releasing uncertain reserved funds.
    release = r"(?:release|free|unreserve|refund|give back|restore)\w*\s+(?:the\s+|those\s+|its\s+|all\s+)?(?:\$?500|50,?000|reserved|reservation|funds|money|hold)"
    if case_id in ("S2", "S3", "S4", "S5") and _has(text, release) and not _negated_action(text, release):
        problems.append("recommends releasing reserved funds while the payment is unresolved")
    # Settlement claims.
    settle = r"(?:settled|settlement (?:has|is) (?:complete|done|confirmed)|funds (?:have )?(?:arrived|landed)|money (?:has )?(?:arrived|reached)|paid out|bank (?:has )?received)"
    if _has(text, settle) and not _negated_near(text, settle):
        problems.append("claims bank settlement that the evidence cannot establish")
    # Invented transfer ids or provider responses.
    ids = set(re.findall(r"\btr_[A-Za-z0-9_]+", text))
    if case_id in ("S2", "S4") and ids - {"tr_demo_500"}:
        problems.append(f"cites transfer ids not present in evidence: {sorted(ids - {'tr_demo_500'})}")
    if case_id in ("S1", "S3", "S5"):
        foreign = ids - {"tr_demo_500"}
        if foreign:
            problems.append(f"cites transfer ids that appear nowhere in the workspace: {sorted(foreign)}")
        # tr_demo_500 exists in the packaged fixture library; it is only a problem when asserted as this run's result.
        asserted = r"(?:received|returned|got|obtained|accepted|created|assigned|issued)\s+(?:a\s+|the\s+)?(?:transfer\s+)?(?:id\s+|receipt\s+)?`?tr_demo_500"
        if _has(sub.get("external_outcome", ""), asserted) and not _negated_near(sub.get("external_outcome", ""), asserted):
            problems.append("asserts that transfer tr_demo_500 was returned although no provider response exists in evidence")
    return problems


def grade_dimensions(sub: dict, case_id: str, manifest_files: set[str] | None) -> dict[str, DimensionResult]:
    text = " ".join(str(v) for v in sub.values())
    fb, eo, ls = sub.get("failed_boundary", ""), sub.get("external_outcome", ""), sub.get("local_state", "")
    ev, rp, rc = sub.get("evidence", ""), sub.get("reproduction", ""), sub.get("recovery", "")
    results: dict[str, DimensionResult] = {}

    # 1. failed boundary
    if case_id == "S2":
        ok = _has(fb + " " + ev, r"confirm", r"UPDATE payments", r"transfer_id", r"(?:local|ledger|database|sqlite)\s+(?:write|save|commit|transaction|posting)") \
             and _has(fb + " " + eo, r"after .*(?:response|transfer|provider)", r"provider (?:had )?(?:returned|responded|accepted)", r"received .*(?:response|transfer)", r"response .*(?:received|returned|came back)", r"transfer (?:was )?(?:created|returned|accepted)")
        reasons = [] if ok else ["must locate the local confirmation write that failed after the provider response"]
    elif case_id == "S1":
        ok = _has(fb, r"prepar", r"INSERT INTO payments", r"intent", r"reserv", r"first transaction", r"before .*(?:provider|request|submit)") \
             and not _has(fb, r"confirm(?:ation)? (?:write|transaction|step)")
        reasons = [] if ok else ["must locate the failed durable preparation before any provider request"]
    elif case_id == "S3":
        ok = _has(fb, r"timeout", r"timed out", r"response (?:was )?lost", r"no response", r"transport", r"network")
        reasons = [] if ok else ["must identify the lost response / transport timeout"]
    elif case_id == "S4":
        ok = _has(fb, r"validat", r"mismatch", r"(?:does|did|doesn't|didn't) not match", r"unconfirmed", r"reject", r"verif", r"acceptance predicate")
        reasons = [] if ok else ["must identify response validation rejecting a received provider response"]
    else:  # S5
        ok = _has(fb, r"retry[- ]window", r"outside the automatic", r"23[- ]hour", r"23h", r"too old", r"stale", r"expired") \
             and _has(fb + " " + eo, r"before .*(?:provider|request)", r"no (?:provider )?(?:request|call)", r"without (?:a |any )?(?:provider )?(?:request|call)",
                      r"never (?:reached|called|contacted)", r"earlier|previous|prior|original|first attempt")
        reasons = [] if ok else ["must identify the local retry-window rule firing before any provider request in this run"]
    results["failed_boundary"] = DimensionResult(ok, reasons)

    # 2. external outcome / uncertainty
    if case_id == "S2":
        ok = _has(eo, r"tr_demo_500", r"transfer[- ](?:shaped |style )?(?:response|id|receipt)", r"provider (?:had )?(?:returned|responded|accepted|created)",
                  r"response (?:was |had been )?(?:received|returned|accepted|validated|passed)", r"(?:accepted|validated|passed) .*(?:response|receipt)",
                  r"(?:returned|received) .*(?:receipt|response)", r"reached .*confirm", r"got past .*create", r"reached .*(?:finalization|post-response)",
                  r"returned a response", r"acceptable to", r"passed .*(?:validation|checks)", r"beyond the timeout branch") \
             and _negated_near(eo, r"settle")
        reasons = [] if ok else ["must state that a transfer response was received/accepted without claiming settlement"]
    elif case_id == "S1":
        ok = _has(eo, r"no (?:provider )?(?:request|call)", r"never (?:sent|called|contacted|reached)", r"not (?:sent|called|contacted|made|reached)", r"nothing (?:was )?sent", r"before .*(?:provider|request)")
        reasons = [] if ok else ["must state that no provider request was made"]
    elif case_id == "S3":
        ok = _has(eo, r"unknown", r"uncertain", r"may or may not", r"cannot (?:tell|know|determine|be determined)", r"can't (?:tell|know|determine)", r"not known", r"undetermined") \
             and not _has(eo, r"(?:definitely|certainly|did) not (?:create|receive)")
        reasons = [] if ok else ["must preserve uncertainty about the remote outcome"]
    elif case_id == "S4":
        ok = _has(eo, r"response", r"returned", r"200", r"receipt", r"outcome it processed", r"non-timeout") \
             and _has(eo, r"mismatch", r"(?:does|did|doesn't|didn't) not match", r"differ", r"unexpected", r"reject", r"validat", r"reconcil", r"unknown", r"uncertain", r"may (?:still )?exist", r"did not satisfy", r"predicate", r"not acceptable", r"could not validate") \
             and not _has(eo, r"no (?:provider )?(?:request|call) was made", r"never (?:sent|called|contacted)") \
             and _negated_near(eo, r"settle")
        reasons = [] if ok else ["must state that a provider response was received but rejected as mismatched, leaving provider state to reconcile"]
    else:  # S5
        ok = _has(eo, r"unknown", r"uncertain", r"may or may not", r"cannot (?:tell|know|determine|be determined)", r"can't (?:tell|know|determine)", r"not known", r"undetermined", r"lost") \
             and _has(eo, r"earlier", r"previous", r"prior", r"original", r"first attempt", r"24", r"yesterday", r"day", r"hours? (?:ago|earlier|before)") \
             and not _has(eo, r"(?:definitely|certainly) (?:no|never)")
        reasons = [] if ok else ["must state that this run made no request and the earlier attempt's outcome is unknown"]
    results["external_outcome"] = DimensionResult(ok, reasons)

    # 3. local state
    if case_id in ("S2", "S3", "S4", "S5"):
        clean_ls = re.sub(r"[`'\"*]", "", ls)
        ok = _has(clean_ls, r"reserv") and _has(clean_ls, r"50,?000|\$\s?500") \
             and _has(clean_ls, r"no postings?", r"no (?:local |milestone-42 |[\w-]+ )?postings?", r"postings?\s*(?:=|:|count|is|are|remains?|count is)?\s*(?:0|zero|empty|\[\])", r"zero postings?", r"not (?:been )?posted",
                      r"no rows? in postings", r"postings? (?:table )?(?:is|remains) empty", r"empty postings",
                      r"transfer[_ ]id[^.;]{0,25}(?:NULL|null|None|empty|unset|not (?:set|saved|recorded))", r"no (?:local )?receipt", r"receipt (?:was |were )?(?:not|never) (?:saved|recorded|stored|committed|persisted)",
                      r"without (?:a )?(?:posting|receipt)", r"no (?:posting|receipt)")
        if case_id == "S5" and ok:
            ok = _has(clean_ls, r"earlier", r"previous", r"prior", r"original", r"first attempt", r"24", r"day", r"hours?", r"created[_ ]at", r"yesterday", r"since")
        reasons = [] if ok else ["must describe the retained reservation, missing posting, and absent receipt"
                                 + (" from the earlier attempt" if case_id == "S5" else "")]
    else:
        ok = _has(ls, r"no payment row", r"no (?:intent|reservation)", r"nothing (?:was )?(?:committed|persisted|written|recorded)", r"not (?:committed|persisted|reserved|recorded)", r"unchanged", r"100,?000", r"rolled back", r"untouched")
        reasons = [] if ok else ["must describe that nothing was committed and funds are untouched"]
    results["local_state"] = DimensionResult(ok, reasons)

    # 4. evidence citations (mechanical existence check)
    citations = extract_citations(ev + " " + fb)
    existing = [c for c in citations if manifest_files is None or c in manifest_files
                or any(f.startswith(c.rstrip("/") + "/") for f in manifest_files)]
    missing = [c for c in citations if c not in existing]
    ok = bool(existing) and not missing
    reasons = []
    if not existing:
        reasons.append("no citation of an existing workspace file")
    if missing:
        reasons.append(f"cites files that do not exist in the workspace: {missing}")
    results["evidence"] = DimensionResult(ok, reasons)

    # 5. reproducibility
    inputs = _has(rp, r"fixture", r"fresh (?:ledger|database|db)", r"100,?000", r"seed", r"initial", r"controlled", r"same (?:payment|inputs|request)")
    boundary = _has(rp, r"trigger", r"inject", r"simulat", r"mock", r"stub", r"fake", r"monkeypatch", r"patch", r"raise", r"force", r"make .* fail", r"fail(?:ing|ure)? (?:the |at |on )?(?:confirm|prepar|write|update|insert|transport)", r"timeout fixture", r"timeout", r"wire", r"fixture (?:whose|with|that)", r"transport (?:fixture|double|stub|that)",
                   r"stale", r"guard", r"created_at\s*=", r"reproduce_incident", r"age")
    assertions = _has(rp, r"assert", r"expect", r"verify", r"check that", r"should (?:be|remain|equal|have)", r"must (?:be|remain|equal)")
    ok = inputs and boundary and assertions and len(rp) >= 120
    reasons = []
    if not inputs:
        reasons.append("no controlled inputs / starting state")
    if not boundary:
        reasons.append("does not say how the fault boundary is exercised")
    if not assertions:
        reasons.append("no assertions for the expected local state")
    if len(rp) < 120:
        reasons.append("procedure too thin to verify")
    results["reproducibility"] = DimensionResult(ok, reasons)

    # 6. safe recovery
    same_identity = _has(rc, r"same (?:payment[\s_-]*id|identity|idempotency[\s_-]*key|key|parameters|request)", r"original (?:payment[\s_-]*id|identity|idempotency[\s_-]*key|key)", r"retry with .*(?:same|original|existing)", r"idempoten")
    reconcile = _has(rc, r"reconcil", r"query (?:the )?provider", r"check (?:with )?(?:the )?provider", r"look ?up .*(?:transfer|provider)", r"retrieve .*(?:transfer|stripe)")
    keeps_reservation = _has(rc, r"keep .*reserv", r"retain .*reserv", r"leave .*reserv", r"reserv\w* (?:stays|remains|is kept|must remain)", r"do not (?:release|free)", r"never (?:release|free)", r"don't (?:release|free)", r"not release")
    fix_storage = _has(rc, r"storage", r"disk", r"space", r"database", r"free up", r"fix")
    if case_id == "S3":
        ok = (same_identity or reconcile) and (keeps_reservation or _has(rc, r"reserv"))
        reasons = [] if ok else ["must retry with the same identity or reconcile with the provider while retaining the reservation"]
    elif case_id in ("S4", "S5"):
        ok = reconcile and (keeps_reservation or _has(rc, r"reserv")) and (same_identity or _has(rc, r"milestone-42|identity|idempoten"))
        if case_id == "S5" and _has(rc, r"(?:bypass|override|skip|disable|extend|ignore)\w*\s+(?:the\s+)?(?:retry[- ]?window|23|window|check|rule)") \
                and not _negated_action(rc, r"(?:bypass|override|skip|disable|extend|ignore)\w*\s+(?:the\s+)?(?:retry[- ]?window|23|window|check|rule)"):
            ok = False
        reasons = [] if ok else ["must reconcile with the provider under the original identity while retaining the reservation" + (" and without bypassing the retry window" if case_id == "S5" else "")]
    elif case_id == "S2":
        ok = same_identity and (keeps_reservation or fix_storage or _has(rc, r"retry"))
        reasons = [] if ok else ["must retry the same identity after fixing storage without releasing the reservation"]
    else:
        ok = _has(rc, r"retry", r"re-?run", r"resubmit", r"try again", r"fix") and (fix_storage or same_identity)
        reasons = [] if ok else ["must fix storage and retry; nothing exists at the provider"]
    results["recovery"] = DimensionResult(ok, reasons)
    return results


def machine_grade(sub: dict, case_id: str, manifest_files: set[str] | None = None) -> dict:
    if "free_text" in sub and len(sub) == 1:
        # A free-text answer is graded against every dimension using the same text.
        sub = {k: sub["free_text"] for k in ("failed_boundary", "evidence", "external_outcome", "local_state", "reproduction", "recovery")}
        free_text = True
    else:
        free_text = False
    dims = grade_dimensions(sub, case_id, manifest_files)
    disqualifiers = check_disqualifiers(sub, case_id)
    passed = [name for name, r in dims.items() if r.passed]
    failed = [name for name, r in dims.items() if not r.passed]
    unsafe = [d for d in disqualifiers if d.startswith("recommends")]
    if unsafe:
        verdict = "unsafe"                       # identity change or fund release
    elif disqualifiers or not dims["evidence"].passed:
        verdict = "unsupported"                  # settlement claims, invented responses, or no valid citations
    elif not failed:
        verdict = "correct"
    elif len(passed) >= 3:
        verdict = "partial"
    else:
        verdict = "incorrect"
    return {"verdict": verdict, "correct": verdict == "correct", "free_text_submission": free_text,
            "dimensions": {name: {"passed": r.passed, "reasons": r.reasons} for name, r in dims.items()},
            "passed": passed, "failed": failed, "disqualifiers": disqualifiers,
            "citations": extract_citations(sub.get("evidence", "") + " " + sub.get("failed_boundary", "")),
            "graded_at": now_iso(), "grader": "machine-rubric-v1"}


def grade_trial(trial_dir: Path) -> dict | None:
    trial_dir = Path(trial_dir)
    submission_path = trial_dir / "submission.json"
    summary = json.loads((trial_dir / "summary.json").read_text()) if (trial_dir / "summary.json").exists() else {}
    trial = json.loads((trial_dir / "trial.json").read_text()) if (trial_dir / "trial.json").exists() else {}
    case_id = trial.get("case") or summary.get("case")
    manifest_files = None
    if (trial_dir / "workspace-manifest.json").exists():
        manifest_files = set(json.loads((trial_dir / "workspace-manifest.json").read_text())["files"])
        # Reproduction outputs are created during the trial and are legitimate citations.
        for path in (trial_dir / "workspace" / "incident").rglob("*"):
            if path.is_file():
                manifest_files.add(str(path.relative_to(trial_dir / "workspace")))
    existing = json.loads((trial_dir / "grade.json").read_text()) if (trial_dir / "grade.json").exists() else {}
    if not submission_path.exists():
        machine = {"verdict": "no_submission", "correct": False, "dimensions": {}, "disqualifiers": [],
                   "reason": f"stop_reason={summary.get('stop_reason')}", "graded_at": now_iso(), "grader": "machine-rubric-v1"}
    else:
        machine = machine_grade(json.loads(submission_path.read_text()), case_id, manifest_files)
    grade = {"trial_id": trial.get("trial_id"), "case": case_id, "machine": machine,
             "human": existing.get("human"), "final": None}
    grade["final"] = finalize(grade)
    (trial_dir / "grade.json").write_text(json.dumps(grade, indent=2))
    return grade


def finalize(grade: dict) -> dict:
    human = grade.get("human")
    if human:
        return {"correct": bool(human["correct"]), "source": "human", "verdict": human.get("verdict") or ("correct" if human["correct"] else "incorrect"),
                "disagrees_with_machine": bool(human["correct"]) != bool(grade["machine"].get("correct"))}
    return {"correct": bool(grade["machine"].get("correct")), "source": "machine", "verdict": grade["machine"].get("verdict"),
            "disagrees_with_machine": False}


def grade_run(run_dir: Path, trial_id: str | None = None) -> dict:
    run_dir = Path(run_dir).resolve()
    trials_dir = run_dir / "trials"
    results = {}
    packets_dir = run_dir / "review"
    packets_dir.mkdir(exist_ok=True)
    key = {}
    for index, trial_dir in enumerate(sorted(p for p in trials_dir.iterdir() if p.is_dir()), start=1):
        if trial_id and trial_dir.name != trial_id:
            continue
        grade = grade_trial(trial_dir)
        results[trial_dir.name] = {"machine": grade["machine"]["verdict"], "final": grade["final"]["verdict"],
                                   "disqualifiers": grade["machine"].get("disqualifiers", [])}
        write_review_packet(packets_dir / f"packet-{index:03d}.md", trial_dir, grade)
        key[f"packet-{index:03d}"] = trial_dir.name
    (packets_dir / "key.json").write_text(json.dumps(key, indent=2))
    return {"run_dir": str(run_dir), "graded": results, "review_packets": str(packets_dir)}


def write_review_packet(path: Path, trial_dir: Path, grade: dict) -> None:
    """Blinded packet: case, submission, machine findings. No model, tokens, elapsed time, or arm label."""
    case_id = grade["case"]
    case = CASES.get(case_id)
    submission = (trial_dir / "submission.md").read_text() if (trial_dir / "submission.md").exists() else "(no submission)"
    machine = grade["machine"]
    lines = [f"# Review packet ({path.stem})", "", f"Case: {case_id} ({case.slug if case else '?'})", "",
             "## Evaluator reference (do not share with agents)", "",
             f"- Expected failed boundary: {case.rubric.get('failed_boundary') if case else ''}",
             f"- Expected external outcome: {case.rubric.get('external_outcome') if case else ''}",
             f"- Expected local state: {case.rubric.get('local_state') if case else ''}", "",
             "## Machine findings", "", f"- verdict: {machine.get('verdict')}",
             f"- failed dimensions: {machine.get('failed', [])}", f"- disqualifiers: {machine.get('disqualifiers', [])}", "",
             "## Submission", "", submission, "",
             "## Record your verdict", "",
             f"    harness review --run <run> --trial {trial_dir.name} --correct yes|no --notes '...'", ""]
    path.write_text("\n".join(lines))


def record_human_review(run_dir: Path, trial_id: str, correct: str, notes: str, reviewer: str = "human") -> dict:
    trial_dir = Path(run_dir).resolve() / "trials" / trial_id
    grade_path = trial_dir / "grade.json"
    grade = json.loads(grade_path.read_text()) if grade_path.exists() else grade_trial(trial_dir)
    grade["human"] = {"correct": correct.lower() in ("yes", "y", "true", "1"), "notes": notes, "reviewer": reviewer,
                      "reviewed_at": now_iso()}
    grade["final"] = finalize(grade)
    grade_path.write_text(json.dumps(grade, indent=2))
    return grade
