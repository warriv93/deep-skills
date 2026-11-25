# Phase 5 — Retro

A landed milestone's **friction** becomes **findings**, so the skills and agents behind it stop repeating the same mistakes and the same expensive work. Each finding goes to the run's findings ref on `FINDINGS_REMOTE` ([podium_ext.py](podium_ext.py)), where a weekly pass drafts fixes for the ones that recur.

1. `podium handoff <id> retro`. It first records the quality gate's Design rows as a `design-<repo>` finding per repo (`FINDING design-<repo> recorded`), so decay that recurs across milestones reaches `/deep-garden`. `SKIP no friction` → step 3.
2. `PROMPT <file> model=<model>` → start it as phase-1-plan.md's Hand-off does. It records each finding with `podium finding add` and replies with its `FINDING` lines or `no findings`. Pass them to the user in one message, as they are.
3. Suggest the next milestone in chat with the Podium link, as a bare run does (SKILL.md, Map first), and start nothing. Keep the watcher running: a Plan press or `/orchestrate-deep-plans <id>` starts it here, and its planning runs in a fresh subagent from the run's state on disk (phase-1-plan.md, Hand-off), so this conversation carries only hand-overs and replies into the next milestone.

Done when the retro printed `SKIP no friction` or its subagent's reply is in chat, and the next milestone is suggested.
