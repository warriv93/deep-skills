---
name: deep-plan
description: Build one feature end to end in an existing codebase — recon, grill the spec, UI mock sign-off, deep-modular architecture, SDD+TDD slices, quality gates, verification loop, merge. Use for "/deep-plan", "plan and build feature X", or a milestone handed over by /deep-app-plan.
argument-hint: <feature description>
---

# /deep-plan

Drive one feature into an existing project, from idea to a verified, spec-conformant implementation, using deep modular architecture, SDD and TDD. A brand-new app with no repo or deploy target belongs to `/deep-app-plan`.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

## Ledger — `.deep-plan/`

The **ledger** is `.deep-plan/state.md`: current phase, one line per slice (`- [x] <slice> — <sha> — PASS`), attempt counts, gate status lines. Keep it ≤60 lines; verbose output goes to sibling files:

| File | Written in |
| --- | --- |
| `recon-note.md` | Phase R |
| `spec-brief.md` | Phase 0 (amended by 0.5) |
| `mock/` | Phase 0.5 |
| `architecture.draft.md` | Phase 0, background (optional) |
| `architecture.md` | Phase 1 |
| `contract.cmds` | Phase 1: the pinned contract, one gate per line |
| `contract.logs/` | one log per gate, from every contract run (overwritten) |
| `findings-phase-3.md`, `findings-phase-4.md`, `findings-phase-4-review.md` | `/deep-qa` at that gate |

Start every turn by reading the ledger and resuming from it; create it if missing.

**Checkpoint** = every artifact of the phase is on disk and committed (Shared rules, Commits), and the ledger names the next phase, so a fresh context can resume from disk alone. End each phase on a checkpoint.

## Orchestrated runs

`.deep-plan/podium/podium.json` exists → `/orchestrate-deep-plans` owns this run:

- Change `podium.json` and `events.jsonl` only through the `podium` command (orchestrate-deep-plans' SKILL.md, `podium`), with `--dir <main checkout>/.deep-plan` when this run works in another worktree. At every checkpoint: `set milestone:<id> phase=<phase> artifacts+=<{name, path, phase}> --event phase phase=<phase>`, `<id>` this run's milestone (another one can be the active one), one `artifacts+=` per new planning file.
- Before every question to the user and every sign-off gate, run `podium human`. Unavailable or mobile → orchestrate-deep-plans' rule for that mode (its SKILL.md, The human) replaces or trims asking.
- While a sign-off gate waits on the user, `set . needsYou=<{reason}>`; `set . needsYou=null` on sign-off.
- Where a phase would ask the user to `/clear` and re-invoke `/deep-plan`, stop at that checkpoint and return to `/orchestrate-deep-plans` instead: it carries on in a fresh subagent.
- After Phase 2's checkpoint, return to `/orchestrate-deep-plans`. It builds the slices as stories and re-enters Phase 3 at its quality gate.

## Shared rules

- **Contract runs:** one call, `~/.claude/skills/deep-plan/scripts/gates.sh . --logs .deep-plan/contract.logs [--only <gate>,…]`. It runs every gate of the contract (`.deep-plan/contract.cmds`) and prints a `PASS`/`FAIL` line per gate, then the last 40 lines of each failing one; read a full log only when that tail leaves the cause open. Exit 0 is green. `--only` re-runs the failed gates.
- **Subagent protocol:** every *cheap* or *strong subagent*, and every other spawn, follows [subagent-protocol.md](subagent-protocol.md): model, brief and reply cap. Read it before the run's first spawn.
- **Code speaks for itself:** everything that lands in the code (comments, test names, identifiers, log messages, docs outside `.deep-plan/`) describes the product and the code in their own terms. It never names planning ids (slice, story, milestone, decision or wave ids such as S3, M2, D7), the brief, the spec or the ledger: they go stale and a reader of the code doesn't need them. Default to no comments; add one only for a non-obvious external constraint, a third-party workaround, or a reason the code can't show. Planning ids belong in `.deep-plan/` and commit trailers only.
- **Commits:** one commit per green slice, conventional message. Every checkpoint commits too: the phase's files from the ledger table and `state.md`, staged by name, as `docs(plan): <phase> for <feature>`, so `git status` is clean between phases. `contract.logs/` stays out of history: list `/.deep-plan/contract.logs/` in `.git/info/exclude`.
- **Branch:** planning commits go on the feature's branch from the first checkpoint. Phase R on the base branch → `git switch -c plan/<slug>`; Phase 2's speckit branch grows from it, then `git branch -d plan/<slug>`. Finished work merges into the base locally (Phase 6); pushing and a PR happen only on the user's explicit request.

## Phases

Run in order. On entering a phase, read its file (sibling of this `SKILL.md`):

| Phase | File | Done when |
| --- | --- | --- |
| R, 0, 0.5 | [phase-0-grill.md](phase-0-grill.md) | Spec Brief (and mock, if UI) signed off by the user |
| 1 | [phase-1-arch.md](phase-1-arch.md) | `architecture.md` written; the contract exits 0 |
| 2 | [phase-2-sdd.md](phase-2-sdd.md) | `spec.md` + `tasks.md` on disk |
| 3 | [phase-3-exec.md](phase-3-exec.md) | every slice committed green; Phase 3 gate passed |
| 4 | [phase-4-verify.md](phase-4-verify.md) | every success criterion passes, or loop budget spent and reported |
| 5, 6 | [phase-5-6-land.md](phase-5-6-land.md) | debrief given; docs true; ledger closed; merged into the base, or parked |
