# Phase 2 — SDD+TDD Hand-off (speckit)

Invoke the `speckit-custom-plan-tdd-sdd` skill, seeded with `spec-brief.md`, the mock URL (if any) and `architecture.md`, and drive its workflow:

1. `/speckit.constitution` — test-first (TDD) and spec-first (SDD) declared non-negotiable.
2. `/speckit.specify` — `spec.md` plus the feature branch; ≤3 `[NEEDS CLARIFICATION]` markers.
3. `/speckit.clarify` — every remaining marker resolved.
4. `/speckit.checklist` — domain checklists.
5. `/speckit.plan` — technical blueprint following `architecture.md`.
6. `/speckit.tasks` — dependency-ordered `tasks.md`, sliced by user story, tests first in every slice.
7. **Coverage check:** one cheap subagent (sonnet) maps against `tasks.md`, to the task or slice that implements it: each resolved decision and success criterion in `spec-brief.md`, and, under `/orchestrate-deep-plans`, each outcome (`podium decisions --json`) of the decisions the milestone's brief lists under `Rests on: D<n>`. It flags anything unmapped, any non-goal that got a task, and task wording that shrinks a decision ("v1", "for now", "stub", "placeholder", "wired later", "static"). Fix `tasks.md` for each gap, or ask the user when the fix changes scope, then re-run. Done when the subagent returns no gaps.

speckit unavailable → run the equivalent steps inline, or `/to-spec` + `/to-tickets`.

Checkpoint.
