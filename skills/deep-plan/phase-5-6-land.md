# Phase 5 & 6 — Debrief & Landing

## Phase 5 — Human-in-the-loop debrief

Compile from the ledger, `findings-phase-3.md`, `findings-phase-4.md`, `findings-phase-4-review.md` and `git log`:

- **Accomplished:** delivered features mapped to the Spec Brief.
- **Compromises:** divergence from the ideal; every skipped code-review finding.
- **Weak points:** fragile areas, thin test coverage.
- **Inputs needed:** API keys, env vars, secrets, accounts required to run it.
- **Next steps:** concrete follow-ups.

Ask the user: merge, iterate, or park. Merge lands it on the base branch locally, with no PR unless the user asks for one.

## Phase 6 — Land it

Runs when the user answers merge. On iterate, go back to the phase the user names, with the ledger open; on park, record the status in the ledger and stop.

1. **Docs true again:** `CONTEXT.md`, glossary, ADRs, README.
2. **Write back to `CLAUDE.md`:** add new contract commands and layering conventions, tersely. Existing rules are hard-won bug traps — keep every one; edit only lines the shipped code contradicts. When the file grows unwieldy, move domain-specific rules into `.claude/rules/`.
3. **Close the ledger:** mark the final status, then archive or delete this feature's `.deep-plan/` files. `project.md` belongs to `/deep-app-plan` and `domain-stories/` to `/orchestrate-deep-plans`; both stay.
4. **Merge** (on merge): with the steps above committed, `git switch <base> && git merge --no-ff <feature branch>`, rerun the contract on the result, then `git branch -d <feature branch>`. The user asked for a PR instead → `/create-deep-pr`. Pushing the base waits for the user's yes, after `~/.claude/skills/create-deep-pr/scripts/push-preview.sh` output is shown.
