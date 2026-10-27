# Phase 4 — Hand back to deep-plan

1. Set the milestone `phase: "gate"` and append a `phase` event.
2. **Hand the rest to a fresh subagent**, so the build phase's events stay here and out of its context: `podium handoff <id> gate`, then start it from the `PROMPT <file> model=<model>` line as phase-1-plan.md's Hand-off does, and handle its replies the same way. It runs deep-plan from its Phase 3 quality gate (`../deep-plan/phase-3-exec.md`, section "Quality gate") on through its Phases 4, 5 and 6, starting its own review subagents in the foreground. It returns at each sign-off gate, question or context reset, and once landed, in at most 8 lines carrying what steps 3–5 record: the gate's counts and findings file, each criterion's pass, the PR, the landed sha. deep-plan keeps `phase` and `needsYou` current.
3. After the gate, write the milestone `quality.gate` (`findings`, `fixed`, `skipped`, `file`) with `--event gate verdict=<the findings file's verdict> findings=<n>`; the retro reads that verdict. After Phase 4, set each `quality.criteria[].pass`.
4. Its PR opens → `podium set milestone:<id> pr=<{number, url, state}> --event pr number=… state=… url=…`; `podium prs` refreshes the state before you close the milestone.
5. deep-plan lands it → the milestone `status: "done"`, `landedSha`, `shippedAt` (the local date, `YYYY-MM-DD`), `active: null` (another milestone still building: SKILL.md, Running two milestones at once), and a `landed` event. Its box turns gray; with every milestone of every epic done, so does the banner. Linked to Asana → complete its subtask ([asana.md](asana.md), Write back).

Done when the milestone is `done` and deep-plan's ledger is closed. Then Phase 5 ([phase-5-retro.md](phase-5-retro.md)).
