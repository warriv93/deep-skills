# Phase 0 — Adopt a planned project

Runs when `.deep-plan/` holds deep-plan history (ledgers, spec briefs) but no `podium/podium.json`. The project becomes a set of epics whose milestones are its past and planned deep-plan runs. The existing files stay as they are.

The run may already live on origin, synced from another machine: `git ls-remote origin refs/heads/podium-run/<repo> refs/heads/podium` lists a ref → join it with that ref (SKILL.md, _sync_) and carry on with a turn instead of this phase.

1. **Find the runs:** every `state*.md` under `.deep-plan/`, plus runs recorded only inside another ledger's archive section. Name each run from its ledger's title line; filenames can lie.
2. **Inventory** with `Explore` subagents, about five runs each, in parallel, quoting paths:
   - the product briefs (top-level spec briefs) and their numbered items;
   - every milestone: id, title, status, brief, spec folder, ledger, branch, landing commit, ship date, the brief items it covers, and its dependencies, stated or implied by order and shared code;
   - each shipped milestone's stories and their commits (see Messy history);
   - gate results from each `findings-phase-3.md` / `findings-phase-4.md`, or the ledger's gate line;
   - open items: a draft brief's open questions, park reasons, brief items no milestone covers.
   - mocks: HTML mocks under the run dir or repo and claude.ai artifact links in briefs and ledgers, each set as `mock` on the epic or milestone it belongs to.
3. **Group runs into epics:** each product brief is an epic holding the runs planned from it (its own run and the runs that finish it), not every run that touches its flows. Runs no brief covers are grouped by theme, the area of the product they touch (a theme with one run joins its nearest neighbour). Put the grouping to the user in one `AskUserQuestion`: the proposal as the recommended option, with a coarser and a finer alternative in the descriptions.
4. **Map statuses:** landed in git → `done`, whatever the brief's header says; brief written but not signed off → `draft`; parked → `parked`; named for later → `later`; built, then removed by the owner → `dropped` (a milestone or a story).
5. **Write `podium.json`:** register the run and switch its sync on (SKILL.md, `podium`), then `podium set . project=… active=null epics=@<file>` with the confirmed epics and in each every milestone: its stories (`status: "done"`, `tasks`), `quality.gate`, `covers`, `open`, `note`, plus each epic's `uncovered` items and, for each epic or milestone whose `domain-stories/<id>/` exists, its `domainStories` (`status: ready`, a story per `.egn.svg` with the `.story.json` of the same title). Each implied dependency and each guess goes into that milestone's `note`, in words. Then fill every shipped story's commits with `podium commits <range or --no-walk shas> --into <milestone>/<story>`; list a run's commits first with `podium commits <range>` to assign them.
6. **Backfill `events.jsonl`:** `podium backfill` writes `planned`, `commit` and `landed`; add a `status` event for each park or drop date (`set milestone:<id> --event status at=<date> text=…`).
7. **Start the Podium and the watcher** (SKILL.md, Podium). Tell the user in one message: the Podium link, how many milestones landed, what is left (draft, parked, later) and the milestone you suggest next with one line of why, started from the Podium or by naming it, the uncovered brief items, and how many commits belonged to no run.

## Messy history

Git wins over a ledger that disagrees with it; say so in the milestone's `note`.

- **Ids:** the run's own name from its ledger title (`v1`, `M3a`, `M005`; a bare `2b` or `005` gets an `M`). Spec-folder and branch numbers that differ, and renumbering mid-run, go in `note`. Work a ledger calls "later" or "a separate feature" with no name gets `L1`, `L2`, …. Order milestones by first commit, unstarted ones last.
- **No brief or ledger:** the milestone's `brief` is whatever plan or decision document exists.
- **Stories**, in this order of sources: `tasks.md` headings (`## S<n>`, `## Slice N`, speckit `## Phase N: User Story K`); without a `tasks.md`, the slice table in `plan.md` or the architecture file, then ledger lines, then git subjects. Ledger lines outside the slices (post-gate fixes, iterations, on-watch rounds) become one story each, id from the line (`P4`, `It1`, …), depending on the last slice. A slice not shipped inside a shipped milestone keeps `todo` with a `note` saying what waits; only the active milestone's stories can be dispatched.
- **Story `deps`:** from `tasks.md` where it states them, otherwise each story depends on the previous one.
- **Commits:** a merged run's range is `<merge>^1..<merge>^2` (merged sub-branches count). A run with no merge lands at its last commit or its ledger-close commit; `note` says which. A commit two stories share is listed on both, with `--no-stats` on the second. A later commit that amends a landed run becomes story `F<n>` there; any other commit outside a run stays out of the epic and is counted in the step 7 report.
- **`quality.gate`:** `null` when no gate ran. Counts come from the status line of `findings-phase-3.md`, else the ledger or the gate commit (`file` names it); counts nobody stated are tallied and `gate.note` says so. Phase 4's result goes in `gate.note`.
- **`covers`:** the brief items a run touches, possibly none. A run that reverses a brief non-goal says so in `note`.
- **`uncovered`:** brief items no milestone covers, parked and later ones included. Items the owner cut belong in the `note` of the milestone that cut them.

Done when every run the ledgers name is a milestone in a confirmed epic, every shipped story has its commits, and the user has the link. A `REQUEST plan <id>` then starts Phase 1 for that milestone.
