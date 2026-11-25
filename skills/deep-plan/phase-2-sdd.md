# Phase 2 — SDD+TDD Hand-off

Write the spec and the tasks yourself, from `spec-brief.md`, the mock URL (if any) and `architecture.md`, into `specs/<slug>/` on the feature branch (SKILL.md, Shared rules, Branch). A repo with spec-kit's `/speckit.*` commands (`.claude/commands/speckit.*.md`) can run steps 1-5 through them; its `tasks.md` still takes the Tasks format below.

1. **Specify:** `spec.md`, with one `## User Story <n> - <title>` per journey of the Spec Brief (its acceptance scenarios as Given/When/Then), then functional requirements and success criteria; at most 3 `[NEEDS CLARIFICATION]` markers.
2. **Clarify:** every marker resolved, from the Spec Brief or by asking the user.
3. **Checklist:** for each domain the feature touches (API, events, data, security, UX), check the requirements in `spec.md` are complete, unambiguous and testable, and fix the ones that aren't.
4. **Plan:** `plan.md`, the technical blueprint following `architecture.md`.
5. **Tasks:** `tasks.md`, dependency-ordered, sliced by user story, tests first in every slice, in the Tasks format below.
6. **Coverage check:** one subagent on the `coverage` row of [agent-models.md](agent-models.md) maps against `tasks.md`, to the task or slice that implements it: each resolved decision and success criterion in `spec-brief.md`, and, under `/orchestrate-deep-plans`, each outcome (`podium decisions --json`) of the decisions the milestone's brief lists under `Rests on: D<n>`. It flags anything unmapped, any non-goal that got a task, and task wording that shrinks a decision ("v1", "for now", "stub", "placeholder", "wired later", "static"). Fix `tasks.md` for each gap, or ask the user when the fix changes scope, then re-run. Done when the subagent returns no gaps.

7. **Plan page:** with the `plan-summary` skill installed, write the page it describes from `spec-brief.md`, `architecture.md` and `tasks.md` to `.deep-plan/plan.html`. The record is those files, so skip its `~/.claude/plans` paths, and don't publish it: the page stays on this machine. Under `/orchestrate-deep-plans` the Podium hosts the run dir, so register it as an artifact (`podium set milestone:<id> 'artifacts+={"phase":"stories","name":"Plan","path":"plan.html"}'`) and give its Podium URL with the checkpoint; otherwise give its path for `open`. A mobile user gets a screenshot of it instead. Without the skill, skip this step.

Checkpoint.

## Tasks format

`podium breakdown` (orchestrate-deep-plans' phase-2-breakdown.md) and Phase 3 read `tasks.md` in this shape:

````markdown
# Tasks: Invites

## Phase 1: User Story 1 - Send an invite (Priority: P1)

**Goal**: An owner sends an invite by email. Nothing reads it yet.

**Dependencies**: none

**Critical**: yes: the token is a secret.

**Context**: `architecture.md#Invite service`

- [ ] T010 [P] [US1] Write the failing invite test in tests/test_invite.py
- [ ] T011 [US1] Implement the invite service in `src/invites/service.py`

## Phase 2: User Story 2 - Accept an invite (Priority: P2)

**Goal**: The invitee accepts it before it expires.

**Dependencies**: US1

**Critical**: no

**Context**: `architecture.md#Accept flow`

- [ ] T020 [US2] Write the failing accept test, then accept in `src/invites/service.py`
````

- One `## Phase <n>: User Story <k> - <title>` section per slice; `<k>` matches its user story in `spec.md`. `breakdown` turns only these sections into stories, so setup and foundational tasks go in the first story that needs them.
- `**Goal**:` its first sentence becomes the story's summary.
- `**Dependencies**:` the user stories whose code it needs (an interface, a migration, a module), as `US1, US2`, or `none`.
- `**Critical**:` `yes` for money, dates and time zones, concurrency, auth, migrations and core algorithms, else `no`.
- `**Context**:` the sections the slice builds on, comma-separated, each in backticks as `<file>#<heading text>` with the file's path from `.deep-plan/` or from `tasks.md`'s folder.
- Task lines are `- [ ] T<nnn> [P] [US<k>] <what> in <path>`, every file a task touches written as its path from the repo root, tests first.
