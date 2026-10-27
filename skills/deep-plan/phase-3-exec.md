# Phase 3 — Slice Execution & Quality Gate

## Slices

Orchestrated run (see SKILL.md) → the stories replace this section; start at the quality gate.

Work through `tasks.md` one slice at a time, inline in the main context:

1. Load only the current slice's task lines from `tasks.md`.
2. `/tdd`: failing tests first (RED), minimum implementation (GREEN), refactor (IMPROVE).
3. Green → commit, and add the slice's ledger line.

Every slice committed green is not yet done — the gate follows.

## Quality gate

1. **Review:** follow `~/.claude/skills/deep-qa/SKILL.md` in `review` mode against the branch point (`origin/HEAD`), with label `phase-3`. It writes `.deep-plan/findings-phase-3.md`.
2. **Fix what it finds**, refactoring under green tests (`/tdd` IMPROVE); commit as `refactor:` / `fix:`. Verdict `blocked` → put the blocking rows to the user first.
3. Add to `findings-phase-3.md` the reason for each finding skipped. The ledger gets one line: `Quality gate: PASS with N findings in findings-phase-3.md`.
4. Re-run the contract (one `gates.sh` call) until green. Record the HEAD sha in the ledger as `phase-3-end-sha`.
5. Checkpoint.
