# Phase 5 — Retro

A landed milestone's **friction** becomes **findings**, so the skills and agents behind it stop repeating the same mistakes and the same expensive work. Each finding goes to the run's findings ref on `FINDINGS_REMOTE` ([podium_ext.py](podium_ext.py)), where a weekly pass drafts fixes for the ones that recur.

1. `podium handoff <id> retro`. `SKIP no friction` → step 3.
2. `PROMPT <file> model=<model>` → start it as phase-1-plan.md's Hand-off does. It records each finding with `podium finding add` and replies with its `FINDING` lines or `no findings`. Pass them to the user in one message, as they are.
3. Suggest the next milestone in chat with the Podium link, as a bare run does (SKILL.md, Map first), and start nothing. Ask the user to `/clear` and start it with `/orchestrate-deep-plans <id>`: the run's state is on disk, so the next milestone starts from a small context instead of re-reading this one's on every turn. Stop the watcher; the Podium runs on, and a Plan press waits in its queue for the next session. Another milestone still building → keep this session and its watcher, and ask for the `/clear` once that one lands.

Done when the retro printed `SKIP no friction` or its subagent's reply is in chat, and the next milestone is suggested.
