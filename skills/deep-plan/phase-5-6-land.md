# Phase 5 & 6 — Debrief & Landing

## Phase 5 — Human-in-the-loop debrief

Compile from the ledger, `findings-phase-3.md`, `findings-phase-4.md`, `findings-phase-4-review.md` and `git log`:

- **Accomplished:** delivered features mapped to the Spec Brief.
- **Compromises:** divergence from the ideal; every skipped code-review finding.
- **Weak points:** fragile areas, thin test coverage.
- **Inputs needed:** API keys, env vars, secrets, accounts required to run it.
- **Next steps:** concrete follow-ups.

Ask the user through `AskUserQuestion`, three options with merge first: merge (Phase 6, landing it on the base branch locally, with no PR unless the user asks for one), iterate (back to a phase they name), or park (stop with the work on its branch).

## Phase 6 — Land it

Runs when the user answers merge. On iterate, go back to the phase the user names, with the ledger open; on park, record the status in the ledger and stop.

1. **Docs true again:** `CONTEXT.md`, glossary, ADRs, README.
2. **Write back to `CLAUDE.md`:** add new contract commands and layering conventions, tersely. Existing rules are hard-won bug traps — keep every one; edit only lines the shipped code contradicts. When the file grows unwieldy, move domain-specific rules into `.claude/rules/`.
3. **Close the ledger:** mark the final status, then archive or delete this feature's `.deep-plan/` files. `project.md` belongs to `/deep-app-plan` and `domain-stories/` to `/orchestrate-deep-plans`; both stay, and so does `contract.cmds`, the repo's gates for step 4 and every later run.
4. **Merge** (on merge): with the steps above committed, `~/.claude/skills/deep-plan/scripts/land.sh <repo> <feature branch> --base <base>`. It rebases the branch onto the base in a temporary worktree, so the main checkout's own edits stay put, runs the contract there and fast-forwards the base. `LANDED <base> <sha>` → `git branch -d <feature branch>`. `CONFLICT <files>` → resolve them on the branch and rerun; `GATES-FAILED <gates> KEPT <worktree>` → fix them on the branch, remove that worktree and rerun; the same gate failing a second time → stop, leave the base where it is and report the gate with its log, setting `needsYou` while the user is away. The base moves only through `land.sh`, never by a hand-run merge, fast-forward or ref update; `DIRTY <worktree>` → ask the user to commit or stash the edits there. The user asked for a PR instead → `/create-deep-pr`. Pushing the base follows the user's push rule in their `CLAUDE.md`, else waits for their yes; either way, show the `NEXT` line's push preview first.
