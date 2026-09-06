---
title: "Detach architecture docs from Empire by retemplating to myapp"
type: refactor
status: completed
date: 2026-04-23
---

# Detach architecture docs from Empire by retemplating to myapp

> Historical plan: preservation counts below describe the original dotfiles migration, before this repository edition removed the API-spend anecdote.

## Overview

The architecture docs added in commit `dac3dcd` ("Documenting clean architecture") were seeded for the `empire` project. The intent is for these docs to live in `~/dotfiles` as a *template* that can be dropped into any new Rust/SQLite project — so any reference to a single specific project leaks intent. This plan replaces every `empire`-flavored token with a generic `myapp` placeholder, adds a short "Using this template" preamble to `docs/README.md`, and preserves the historical `Cantrip second brain` lineage notes (which are attribution, not a current project).

## Problem Frame

`docs/` currently reads like internal documentation for the `empire` codebase: the README title is "Empire Architecture Notes," the diagram and crate split name `empire-cli`/`empire-server`/`empire-core`/etc., env vars are prefixed `EMPIRE_*`, and the HTTP route is `POST /api/empire`. A reader cloning this template into a new project has to mentally substitute the project name throughout. Worse, anyone landing on the doc could believe `empire` is the canonical example or even the project this repo is about — it isn't.

The fix is a careful multi-form substitution (lowercase, Title Case, UPPERCASE) that keeps the docs reading as concrete, runnable example code rather than placeholder soup, while making it obvious the project name is the substitution point.

## Requirements Trace

**Substitution accuracy:**
- R1. No occurrence of `empire`, `Empire`, or `EMPIRE` remains in `docs/` or `README.md` after this change. (`Cantrip` references are explicitly preserved — see R4.)
- R2. The replacement reads as concrete example code (`myapp-cli`, `MYAPP_DB`, `POST /api/myapp`) rather than fill-in-the-blank tokens — per the user's preference for a runnable-feeling generic name.
- R4. All `Cantrip` references are preserved as historical context — the "second brain" lineage attribution. They are not a current project to detach from.

**Documentation artifact:**
- R3. `docs/README.md` carries a short preamble explaining the doc set is a template and naming the substitution token. The preamble must name `myapp` in all three forms it appears in: lowercase (crate names, prose), `Myapp` (titles/headings), and `MYAPP_*` (env-var prefix).

**Technical integrity:**
- R5. Internal cross-links between docs (e.g., `docs/README.md` linking to `architecture/clean-architecture.md`) continue to resolve. No file renames.

## Scope Boundaries

**In scope:**
- The 6 files touched by `dac3dcd`: `docs/README.md`, `docs/architecture/clean-architecture.md`, `docs/architecture/pact-record-replay.md`, `docs/architecture/ports-and-adapters.md`, `docs/concepts/test-isolation.md`, `docs/concepts/traces.md`.
- The brief mention of `empire` in any of those files' frontmatter (`title:` / `description:`).
- Adding a preamble to `docs/README.md`.

**Out of scope:**
- The top-level `README.md` (the dotfiles README). It was touched by `dac3dcd` but only for unrelated `~/.claude/statusline.sh` notes — `git grep` confirms it has no `empire` references.
- Renaming any files or directories (`docs/architecture/`, `docs/concepts/`).
- Restructuring section content, examples, or wording beyond the name substitution and the new preamble.
- Any Rust source code (none exists in this repo — this is purely a docs change).
- Removing or rewording `Cantrip second brain` attribution.

## Context & Research

### Relevant Code and Patterns

Files in scope (from `git grep -i empire`):

| File | Empire occurrences | Notable forms |
|---|---|---|
| `docs/README.md` | 3 | Title `"Empire Architecture Notes"`, prose `seed empire`, `empire domain` |
| `docs/architecture/clean-architecture.md` | ~30 | Crate prefix in ASCII diagram, `empire-cli` through `empire-pact`, `POST /api/empire`, `EMPIRE_DB`, `EMPIRE_TRACES` |
| `docs/architecture/pact-record-replay.md` | ~9 | `$EMPIRE_TRACES`, `EMPIRE_PORT_LLM`, `empire-pact` crate name |
| `docs/architecture/ports-and-adapters.md` | ~12 | `empire-ports`, `empire-adapters`, `empire-pact`, `empire-core`, `empire-server::build_state()`, `EMPIRE_PORT_<NAME>` |
| `docs/concepts/test-isolation.md` | 3 | `EMPIRE_PORT_<NAME>`, `empire-pact` |
| `docs/concepts/traces.md` | 3 | `$EMPIRE_TRACES`, `empire-pact`, `empire-core` |

`Cantrip` appeared in 4 places in the historical source. The test-isolation anecdote was removed from this repository edition; the remaining historical locations are:
- `docs/README.md:8` — "carried over from the Cantrip second brain"
- `docs/architecture/clean-architecture.md:10` — "Adapted from the Cantrip second brain"
- `docs/architecture/ports-and-adapters.md:41` — "the recurring ports from Cantrip"

### Substitution Map

Three case-sensitive forms must be replaced independently. **Case-sensitivity is the load-bearing requirement** — a case-insensitive sweep would mangle `EMPIRE_DB` into `myapp_DB` and lose the env-var convention. Pass *order* doesn't affect correctness once each pass is case-sensitive (none of `MYAPP`/`Myapp`/`myapp` contains any of `EMPIRE`/`Empire`/`empire` as a substring), so the recommended `EMPIRE` → `Empire` → `empire` order is for reviewability only.

| Source token | Replacement | Where it appears |
|---|---|---|
| `EMPIRE` | `MYAPP` | Env vars: `EMPIRE_DB`, `EMPIRE_TRACES`, `EMPIRE_PORT_LLM`, `EMPIRE_PORT_<NAME>` |
| `Empire` | `Myapp` | Title and H1 in `docs/README.md` |
| `empire` | `myapp` | Crate names (`empire-cli` → `myapp-cli`), HTTP route (`/api/empire` → `/api/myapp`), workspace dir (`empire/`), prose ("empire's domain" → "myapp's domain") |
| `pact`, `Pact`, `empire-pact` | `pact`, `Pact`, `myapp-pact` | `pact` is a *concept* name (the record/replay decorator pattern), not the project — keep `pact` itself, only the `empire-` prefix changes |

### Institutional Learnings

No relevant entries in `docs/solutions/` (directory does not exist in this repo).

### External References

None needed. This is a mechanical text substitution against text the user wrote and committed two days ago.

## Key Technical Decisions

- **Replace with `myapp`, not `<project>` placeholders.** User selected the concrete-name form. Reads as runnable example code; preserves the visual rhythm of `myapp-cli`/`myapp-core`/`myapp-pact`. The "Using this template" preamble (R3) makes it explicit that `myapp` is the substitution point, so no information is lost vs. angle-bracket markers.
- **Case-sensitive, three-pass substitution rather than `sed -i`.** Case-sensitivity is what protects the env-var convention; using three discrete `Edit replace_all` calls per file (rather than one regex sed) keeps each substitution reviewable as its own diff hunk. Pass order is cosmetic — see Substitution Map.
- **Preserve `pact` and `Pact` verbatim.** They name the record/replay *pattern*, not the project. Only the `empire-` prefix on the `empire-pact` crate changes (to `myapp-pact`). Same logic for `Cantrip` (attribution, kept).
- **No file renames.** Cross-link integrity (R5) is trivially preserved by leaving `docs/architecture/clean-architecture.md` etc. in place.

## Open Questions

### Resolved During Planning

- *What replacement style?* → Concrete `myapp` (user selection).
- *Keep or drop the `Cantrip second brain` reference?* → Keep (user selection).
- *Add a "Using this template" preamble?* → Yes, in `docs/README.md` only (user selection).
- *Should the `pact` crate name change?* → Only its `empire-` prefix changes. The `pact` concept name stays.

### Deferred to Implementation

- Exact wording of the new preamble paragraph in `docs/README.md`. Sketch in Unit 2 below; final wording is a copy decision the implementer can make.

## Implementation Units

- [ ] **Unit 1: Substitute project name across the 6 doc files**

**Goal:** Replace every `EMPIRE` / `Empire` / `empire` token with `MYAPP` / `Myapp` / `myapp` across the 6 files in scope, leaving `pact`/`Pact` and `Cantrip` references intact.

**Requirements:** R1, R2, R4, R5

**Dependencies:** None

**Files:**
- Modify: `docs/README.md`
- Modify: `docs/architecture/clean-architecture.md`
- Modify: `docs/architecture/pact-record-replay.md`
- Modify: `docs/architecture/ports-and-adapters.md`
- Modify: `docs/concepts/test-isolation.md`
- Modify: `docs/concepts/traces.md`

**Approach:**
- Per file, run three case-sensitive `Edit replace_all` calls: `EMPIRE` → `MYAPP`, `Empire` → `Myapp`, `empire` → `myapp`. Order is cosmetic; case-sensitivity is what matters.
- Use the Edit tool with `replace_all: true` rather than shell `sed -i` so each substitution is reviewable as its own diff hunk.
- Inside the ASCII diagram in `clean-architecture.md` (lines 14-44), the column widths are sized for the 7-char `empire-` prefix; replacing with the 6-char `myapp-` shortens the boxes by 1 char per line. **Accept the cosmetic shift as-is.** The boxes still align internally and the 1-char delta does not harm readability. (The Risks table mitigation reflects this same firm decision — there is no implementer judgment call here.)
- Verify `Cantrip` and `pact`/`Pact` (the standalone words, not `empire-pact`) are untouched after each file's edits.

**Patterns to follow:**
- Existing Markdown frontmatter style in `docs/README.md` (YAML with `title:` and `description:`).

**Test scenarios:**
- *Verification — happy path:* Run **after all three case-sensitive passes are complete across all six files** (not after each file or each pass). `git grep -i 'empire' docs/ README.md` returns zero matches. (`Cantrip` is case-sensitive and won't match `empire`.)
- *Verification — preservation:* `git grep -n 'Cantrip' docs/` returns the same 4 matches as before the edits (across 4 files: `docs/README.md`, `docs/architecture/clean-architecture.md`, `docs/architecture/ports-and-adapters.md`, `docs/concepts/test-isolation.md`).
- *Verification — pact concept preserved:* `git grep -E '\b[Pp]act\b' docs/` returns the standalone uses (e.g., "Pact record/replay", "the same pact crate"); the `empire-pact` form should now appear only as `myapp-pact`.

**Verification:**
- All six files compile as valid Markdown (no broken code fences from accidental in-fence replacements — verify by spot-reading the ASCII diagram and the Rust code blocks).
- Internal links (`[clean-architecture.md](architecture/clean-architecture.md)`, etc.) still resolve — no file renames means this is automatic, but eyeball the README link list.

---

- [ ] **Unit 2: Add "Using this template" preamble to `docs/README.md`**

**Goal:** Make it explicit at the top of the doc set that this is a reusable template, and that `myapp` (along with its case variants and env-var prefix) is the substitution point for a real project name.

**Requirements:** R3

**Dependencies:** Unit 1 (so the new preamble references the post-substitution token, not `empire`)

**Files:**
- Modify: `docs/README.md`

**Approach:**
- Insert a short section between the H1 (`# Myapp Architecture Notes`, post-Unit-1) and the existing intro paragraph that begins "Reference notes carried over from the Cantrip second brain..."
- The section should: (a) state these are template docs intended to be dropped into a new Rust/SQLite project, (b) name the substitution — `myapp` → real project name, with `MYAPP_*` env vars and `Myapp` for titles/headings — and (c) keep it under 4 sentences. The existing intro paragraph already hints at "the *shape* is what's load-bearing," so the preamble should *complement* that, not duplicate it.

**Technical design:** *Directional sketch — implementer chooses final wording.*

```markdown
## Using this template

These docs are a reusable starting point for a Rust/SQLite project that wants
Clean Architecture with Pact-style record/replay. Drop the `docs/` tree into
a new repo and substitute `myapp` (lowercase in crate names and prose, `Myapp`
in titles, `MYAPP_*` in env vars) with your real project name. The architectural
shape — pure core, port traits, adapter implementations, recording decorator —
is the load-bearing part; the example port methods and crate names are
illustrative.
```

**Patterns to follow:**
- Existing H2 sectioning in `docs/README.md` (e.g., `## Architecture`, `## Concepts`, `## Reading order`).
- Place the new section *before* `## Architecture` so it's the first thing a reader sees after the intro.

**Test scenarios:**
- *Verification — happy path:* The rendered `docs/README.md` shows the new "Using this template" section above `## Architecture`.
- *Verification — no regression:* The existing intro paragraph (Cantrip lineage line) and the existing `## Architecture` / `## Concepts` / `## Reading order` / `## Principles carried over` sections are unchanged in content.

**Verification:**
- The preamble is short (≤ 4 sentences), uses `myapp` in the same forms a reader will see in the rest of the docs, and doesn't restate what the existing intro already says.

---

- [ ] **Unit 3: Final sweep — confirm zero leakage**

**Goal:** Catch anything Units 1-2 missed — frontmatter, code-comment lines, less obvious forms.

**Requirements:** R1, R4

**Dependencies:** Units 1, 2

**Files:**
- Read-only verification across `docs/` and `README.md`

**Approach:**
- Run `git grep -in 'empire' docs/ README.md` — must return zero matches.
- Run `git grep -n 'Cantrip' docs/` — must return the same 4 matches as before (in `docs/README.md`, `docs/architecture/clean-architecture.md`, `docs/architecture/ports-and-adapters.md`, and `docs/concepts/test-isolation.md`).
- Skim the ASCII diagram in `docs/architecture/clean-architecture.md` to confirm box alignment is still readable after the prefix shortened from `empire-` (7 chars) to `myapp-` (6 chars). Per Unit 1 Approach, accept the 1-char shift as-is — do not retighten borders.
- Skim the wiring snippet in `docs/architecture/clean-architecture.md` (the `pub async fn serve` block) and the env-var snippet in `docs/architecture/pact-record-replay.md` to confirm the substitution didn't break Rust syntax inside fenced code blocks.

**Test scenarios:**
- *Happy path:* Both `git grep` commands above return the expected counts (0 for `empire`, 4 for `Cantrip`).
- *Edge case:* No mixed-case oddities like `myappEmpire`, `Empiremyapp`, or accidental `MYAPP` inside non-env-var prose.

**Verification:**
- The diff for the whole change shows only: name substitutions, the new preamble in `docs/README.md`, and (optionally) cosmetic ASCII-box realignment. No content changes elsewhere.

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| ASCII diagram in `clean-architecture.md` becomes misaligned after `empire-` (7 chars) → `myapp-` (6 chars) substitution (1-char delta per line). | Cosmetic-only and accepted as-is per Unit 1 Approach. Unit 3's visual check confirms readability but does not authorize retightening. |
| Case-insensitive replace would corrupt env vars (`EMPIRE_DB` → `myapp_DB`). | Plan mandates three case-sensitive passes (`EMPIRE` → `MYAPP`, `Empire` → `Myapp`, `empire` → `myapp`). Pass order is irrelevant — case-sensitivity is the load-bearing protection. |
| Accidental replacement inside `Cantrip` lineage line or the `pact` concept name. | `Cantrip` and standalone `pact`/`Pact` don't contain the string `empire` in any case form, so they're safe by construction. The only `pact` token that *does* change is the `empire-pact` crate prefix, which is the desired behavior. |
| Future readers misread `myapp` as a real example project. | Unit 2 preamble explicitly frames `myapp` as the substitution point. |

## Sources & References

- Origin commit: `dac3dcd` "Documenting clean architecture" (introduces all 6 files in scope)
- Files in scope: `docs/README.md`, `docs/architecture/clean-architecture.md`, `docs/architecture/pact-record-replay.md`, `docs/architecture/ports-and-adapters.md`, `docs/concepts/test-isolation.md`, `docs/concepts/traces.md`
- Related (out of scope): top-level `README.md` was touched by the same commit but contains no `empire` references.
