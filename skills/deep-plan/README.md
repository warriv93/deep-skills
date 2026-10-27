# /deep-plan

Builds one feature end to end in an existing codebase: recon, a grilled spec, a UI mock, deep-modular architecture, spec and tasks, test-first slices, review gates and a verification loop, then a local merge. Use it for a feature that needs a spec before code, or for a milestone handed over by `/deep-app-plan` or `/orchestrate-deep-plans`.

## What it does

- Keeps its state in the repo under `.deep-plan/`, with a ledger (`state.md`) that lets any later session resume from disk. Every phase ends on a checkpoint commit (`docs(plan): <phase> for <feature>`) on the feature's branch.
- Reads the repo before asking you anything (`CLAUDE.md`, README, `CONTEXT.md`, ADRs, manifests, test setup) and writes a recon note with a reuse list. A feature too big for one session goes to `/wayfinder` instead.
- Grills you through `AskUserQuestion` in proportion to the size, from 1-2 questions for a small change to a full `/grill-with-docs`, and waits for your sign-off on the Spec Brief.
- For UI work, builds a throwaway clickable mock with each open UI question as a switchable alternative, serves it at `http://127.0.0.1:8766/mock/`, and waits for your sign-off.
- Designs deep modules with `/codebase-design` into `architecture.md`, and pins the verification contract (test, typecheck, lint, format, build, e2e) as `.deep-plan/contract.cmds` and runs it with one `scripts/gates.sh` call: a line per gate, the tail of each failing one.
- Writes `spec.md` and `tasks.md` with speckit, then builds slice by slice with `/tdd`, one commit per green slice.
- Runs `/deep-qa` as its quality gate after the slices (defects, spec, design and security), then a verification loop on `/deep-qa`'s running lenses: the contract, the real app through `/run`, accessibility and performance, with a fix loop. Three failed attempts on one failure, or two rounds of gate churn, stop the loop with a report.
- Ends on a debrief (what landed, compromises, weak points, inputs needed, next steps) and asks: merge, iterate or park. Merge updates the docs and `CLAUDE.md`, closes the ledger and merges into the base branch locally.
- Between phases it asks you to `/clear` and re-invoke `/deep-plan`.

Nothing leaves the machine unless you ask. A PR goes through `/create-deep-pr` on your request, and pushing the base waits for your yes.

## Use

```
/deep-plan <feature description>
```

Re-invoking it in the same repo resumes from `.deep-plan/state.md`.

## Install

```sh
./install.sh
```

Run it from the repo root; it symlinks every skill into `~/.claude/skills/`.

Skills it calls:

- `speckit-custom-plan-tdd-sdd` for the spec and tasks (`/to-spec` and `/to-tickets`, or inline steps, without it).
- `/deep-qa` for every review gate and the verification, and through it `code-review` (Matt Pocock's dual-axis review).
- When present: `/wayfinder`, `/grill-with-docs` (`/grilling` and `/domain-modeling`), `/research`, `/prototype`, `frontend-design`, `dataviz`, `/codebase-design`, `/setup-pre-commit`, `git-guardrails-claude-code`, `/tdd`, `/run`, `/security-review`, `/diagnosing-bugs`.
- `/create-deep-pr` when you ask for a PR.

`tests/run.sh` checks `scripts/gates.sh` (the contract in one call) and `scripts/review-pack.sh` (one filtered diff per file for reviewer subagents) against throwaway repos.

Tools: `git` and `python3` (the mock server). Subagents are routed by cost: Haiku for recon search, the security pass and screenshot comparison, Opus for the review gates and `/diagnosing-bugs`.

## Working with the other deep skills

- `/deep-app-plan` hands over milestones; recon then reads `.deep-plan/project.md` and treats its Platform and contract blocks as settled.
- When `.deep-plan/podium/podium.json` exists, `/orchestrate-deep-plans` owns the run: `/deep-plan` reports each checkpoint to the Podium, follows its availability rules before asking you, and returns to the orchestrator after Phase 2 instead of building the slices itself.

Outside Claude Code (Antigravity, Gemini) the skill loads `claude-tool-map` first, which `install.sh` links when `~/.gemini/config/` exists.
