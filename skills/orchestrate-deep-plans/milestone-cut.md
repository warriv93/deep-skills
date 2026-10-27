# Milestone cut

The **cut** splits an epic into milestones, each a thin end-to-end slice a user can notice. Stories stay the build units inside a milestone (phase-2-breakdown.md); these patterns cut milestones only.

Cut when an epic is new (phase-1-plan.md), and when deep-plan reports `TOO BIG <milestone>: <why>`: then cut that milestone alone. Milestones that already exist stay as they are unless the user asks for a re-cut.

## Epic decisions

A question that touches two or more milestones of an epic is settled once, as a **decision**, before the epic is cut; a question that touches one milestone stays in that milestone's grill. The cut and every milestone plan then rest on epic-wide choices made with the user.

1. **List** the epic's open questions that touch two or more milestones. None → go to Patterns. Done when each is listed or the list says none.
2. **Record** each: `podium decision add "<question>" --type <type> --affects "<area or milestone>,…" [--blocked-by D1,D2]`, with `<type>` one of `discussion` (a grill with the user), `research`, `prototype`, `unblock` (access, setup or evidence, never product code). At most 6 open per epic: the tool refuses a 7th, so a question the epic can do without goes to Could drop or defer instead. Done when each question is a `DECISION D<n> open` or a deferral.
3. **Work the frontier.** `podium decisions --epic <id>` prints `FRONTIER` (open, every blocker closed, unclaimed). Claim each (`podium decision claim D<n>`), then by type: `discussion` → grill the user, one decision per round; `research` and `prototype` → a background subagent; `unblock` → an agent, or a checklist for the user. Close it with `resolve "<outcome>"`, `outscope "<why>"` or `invalidate "<why>"`; an answer still missing → `unresolved "<missing>"`, which keeps it open and claimed. The user unavailable → each `discussion` becomes an assumption (SKILL.md, The human), the recommended option taken, and is resolved with it. Done when `podium decisions --epic <id>` prints `STATE CLEAR`.
4. **Cut** as below once `STATE CLEAR`. Each milestone's brief lists the decisions it rests on, as `Rests on: D1, D3`. Done when every new milestone's brief has that line, or no decision touches it.

## Patterns

Walk them yourself, in order, from the epic's brief; the first that splits the work gives each new milestone its `pattern` slug. One milestone when nothing splits: `whole`.

1. `workflow-steps`: the work is a sequence of steps → first a thin version of the whole flow end to end, then enrich steps one milestone at a time.
2. `operations`: it manages something (create, read, update, delete) → one operation per milestone, create or read first.
3. `business-rules`: several rules or policies apply → the simplest rule first, each other rule later.
4. `data-variations`: the same behaviour over several kinds of data → one kind first.
5. `data-entry`: the interface carries the effort → the simplest input first, the rich UI later.
6. `major-effort`: the first case carries most of the cost and the rest reuse it → implement one, then add the rest.
7. `simple-complex`: a simple core is buried in edge cases → the simple version first, each complication later.
8. `defer-performance`: making it fast is separate from making it work → working first, fast later.
9. `spike`: too unknown to cut → a milestone that answers the question and builds nothing, then cut again from its findings.

**Meta-pattern**, when none fits cleanly: find the core complexity, list its variations, reduce them to one complete slice; the variations become later milestones, each with the pattern its variation follows.

## Valuable check

A milestone with no user-visible change (a migration, an API nobody calls yet, a refactor) gets a warning naming where to fold it:

```
⚠ <id> <title>: no user-visible change. Fold into <id> (<pattern>)?
```

## Could drop or defer

List the milestones the epic delivers without: nice-to-haves, later variations, performance, each judged against the epic's brief.

## Proposal

One message: a line per milestone, then the warnings, then the list.

```
M4 Book a slot, card only — workflow-steps
M5 Pay by invoice — data-variations
⚠ M6 Slot table migration — major-effort
⚠ M6 Slot table migration: no user-visible change. Fold into M4 (workflow-steps)?
Could drop or defer: M5 (card covers the launch)
```

Done when every milestone has a pattern and a verdict, every unvaluable one a warning, and the list names each candidate or says none.

## Sign-off

One sign-off before any milestone of the cut is planned: `AskUserQuestion` when available, its first question **Approve** (Recommended) / **Move items** (the user says which into which), then one question per warning, **Fold** (Recommended) / **Keep**, with a reason in the notes; at most three questions per call, so more warnings take more calls. Without `AskUserQuestion`, the same questions in text. Unavailable → each answer is an assumption (SKILL.md, The human), the recommended option taken.

Done when every warning is answered and the cut is approved.

## On approval

1. **Create** each new milestone: `podium set epic:<epic> 'milestones+={"id":"<id>","title":"<title>","status":"todo","deps":[…],"cut":{"pattern":"<slug>","valuable":<true|false>}}'` with an event. Done when every milestone of the cut is in `podium.json` with its `cut`.
2. **Fold** each accepted warning or moved item: `podium move <m> --to <target> --pattern <p>`, then append to the target's brief a section `## Moved in from <m>` quoting the moved milestone's scope as input for its grill, not as decisions. An Asana-linked moved milestone → ask the user before closing its subtask ([asana.md](asana.md)), and add its link to the target's brief. Done when each prints `MOVED <m> → <target>` and its target's brief holds the section.
3. **Override** each kept warning: `podium set milestone:<id> 'cut={"pattern":"<slug>","valuable":false,"kept":"<why>"}'`, and on every milestone that needs it a `waitsFor` entry on it (SKILL.md, Waiting for another milestone). Done when each kept milestone has `cut.kept` and each milestone needing it waits for it.
