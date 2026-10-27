# Phase 4 — Verification Loop

Done when every success criterion in `spec-brief.md` passes — or the loop budget is spent and reported.

1. **Verify:** follow `~/.claude/skills/deep-qa/SKILL.md` in `verify` mode with label `phase-4`: the full contract with coverage and e2e, every P1 journey in the real app, accessibility and performance. It writes `.deep-plan/findings-phase-4.md`.
2. **Fix loop:** for each failure or unmet requirement, fix, re-test, re-commit.
   - Each hypothesis starts from the last green slice commit: a failed attempt, or one that breaks tests, is discarded with `git reset --hard <last-green-sha>` before the next.
   - Hard failures and regressions → `/diagnosing-bugs` as a strong subagent.
   - **Loop budget:** count attempts per failure in the ledger. At 3 failed attempts on one failure, or 2 rounds of gate churn, stop and report to the user.
3. **Second review gate:** Phase 3's review with `<phase-3-end-sha>` as its base and label `phase-4-review`, so it covers only what the loop changed, security included.
4. Checkpoint.
