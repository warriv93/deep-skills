# Phase 3 — Build the stories

Everything here acts on one milestone: the active one, or a second one building beside it, whose stories every command names `<milestone>/<id>` (SKILL.md, Running two milestones at once). A story is **ready** when it is `todo`, not handed off, and every id in `deps` and `overlapAfter` is `done` (`podium ready [--milestone <id>]`). A story is **handed off** while the user runs it in a session of their own (the Podium's copy button writes `handoffs.json`, its ✕ takes it back); that session reports through the story's progress file like any agent, so act on its lines as below. A handed-off story has no agent to stop; `podium land` releases it after `MERGED`, and after `FAILED` release it with `curl -s -X DELETE <podium>/handoff/<milestone>/<id>`. A **wave** is the set of a milestone's stories that are ready at the same moment.

## Watcher events

An event names a story by its bare id; `<milestone>` below is the milestone that holds it.

| Line | Act |
| --- | --- |
| `REQUEST assign <milestone>/<id>` | `podium launch <milestone>/<id>` (Dispatch); `SKIP` → append a `request` event saying what it waits on. A bare `<id>`, from an older Podium tab, is the active milestone's |
| `REQUEST build-all <milestone>` | `podium set milestone:<milestone> buildAll=true`, then `podium launch` every id `podium ready --milestone <milestone>` prints, as `<milestone>/<id>` |
| `REQUEST stop <milestone>` | `podium set milestone:<milestone> buildAll=false`; running stories finish |
| `REQUEST plan <id>` | append a `request` event saying `<id>` waits for the active milestone |
| `REQUEST proceed <milestone>` | the user chose to go ahead without the milestone it waits for: `podium set milestone:<milestone> waitsForAck=true`, then carry on, mocking what the other milestone would provide (SKILL.md, Waiting for another milestone) |
| `REQUEST confirm <n>[,<n>…]` | the user confirmed those assumptions in the Podium (Confirm all sends every open one): `podium settle <ids> confirmed` |
| `REQUEST reverse <n> [note=…]` | the user reversed it: settle it as `reversed` and do the rework, the note saying what they want instead |
| `REQUEST asana [<epic>] note=<link>` | the user linked Asana in the Podium: map it ([asana.md](asana.md), Link) |
| `REQUEST domain-story <id>` | draw that epic or milestone (below) |
| `REQUEST asana-done <milestone> note=<drop\|keep>` | the user answered "Done in Asana?": skip or keep it ([asana.md](asana.md), Refresh) |
| `REQUEST share` | the user pressed Share: share the run, or reply with the colleague's steps again (SKILL.md, Share) |
| `PROGRESS <id> … COMMITTED <sha>` | merge it at once (below): the merge re-runs the contract, which is the check. Several `COMMITTED` lines in one batch → one `podium merge <milestone>/<id>… --land --next` |
| `PROGRESS <id> … FAILED <why>` | a failed attempt (below) |
| `IDLE <id>`, or a subagent finished, without `COMMITTED` | check it (Idle, below) |
| `PERMISSION <id> <tool>` | unavailable and the story's first → deny it (`respond_to_permission`) with "the user is away: find another way, or log FAILED", then `set <milestone>/<id> denied+=1 --event denied tool=<tool>`. Otherwise flag it: `status: "approval"`, `needsYou: {reason: "<id> waits for approval: <tool>", story}`, `approval` event |
| `PERMISSION-CLEARED <id>` | `status: "working"`, `needsYou: null` |
| `SYNCED <who> <summary>` | another person's saved progress arrived: report it in one line |
| `REVIEWED <milestone> [<repo>]#<n> by=<who>` | a colleague ticked Looked at it on your draft PR: tell the user in one line, read the PR's review (`gh pr view <n> --comments`) and offer to address it, or to mark it ready when nothing is left |

With a milestone's `buildAll` on, its next wave starts when every story of its current wave is merged.

## Idle

An agent sits idle while its contract or tests run in the background, for many minutes when two milestones build on one machine, so idle alone is no failure.

1. Look for its work first: `podium peek <milestone>/<id>` prints its last progress stage and how long ago, and for an `Agent` tool story the processes working in its worktree. For a Paseo story, `lsof -d cwd 2>/dev/null | grep -F <worktree>` lists them (the agent's own `claude` among them). A `gates.sh`, build or test process running there → wait for its next event.
2. Nothing running and no `COMMITTED` line → nudge the agent once (Paseo `send_agent_prompt`, or `SendMessage` to a subagent): "Finish the story: log COMMITTED <sha>, or FAILED <why>."
3. Idle again with neither line → a failed attempt, reason "stopped without committing".

## Domain stories

The Podium's Domain story and Redraw buttons ask for an epic or a milestone drawn as domain stories, any time, whatever is active. `<target>` is `epic:<id>` or `milestone:<id>`; the stories go in `.deep-plan/domain-stories/<id>/`.

1. `podium set <target> domainStories.status=drawing`.
2. Dispatch one background subagent, Sonnet, in the main checkout, with the prompt for the target. Both end: "Write each story as `<Title>.story.json` and its `<Title>.egn.svg` into `.deep-plan/domain-stories/<id>/`, replacing what is there. No one answers questions: settle the read-back from the specs, and put each guess in the open-questions file. Return each story's title and the two paths, and the open-questions path if written."
   - **Epic:** "Use the `deep-domain-storytelling` skill in Draft mode to draw the process `<epic spec>` and the specs of its milestones change: the process as it runs today, read from the code and the recon notes, with every sentence the epic adds or alters marked `changed` (it draws them green). When the epic moves steps between actors or removes them, draw separate AS-IS and TO-BE stories instead, as the skill says under Showing where a change lands." Its milestones already drawn → add: "Use the actors, work objects and wording of `<their .story.json paths>`."
   - **Milestone:** "Use the `deep-domain-storytelling` skill in Draft mode to draw what milestone `<id>` changes, from `<its brief>` and `<its spec>`: only the stories it touches, and in each the sentences it adds or alters, marked `changed`, plus the sentences that lead into and out of them, so each story still runs from its trigger to its outcome. Sentences later milestones add stay out. When the milestone moves steps between actors or removes them, draw separate AS-IS and TO-BE stories instead, as the skill says under Showing where a change lands." The epic's `domainStories` are `ready` → add: "Start from the epic's stories `<their .story.json paths>`: keep their actors, work objects, icons and wording, read the process as it runs today from the code only where they don't cover it, and name the epic story each one starts from in its description." Otherwise → add: "Read the process as it runs today from the code and the recon notes."
3. It returns → `podium set <target> domainStories.status=ready domainStories.at=now domainStories.stories=@<file> [domainStories.questions=<path>] --event domain-story <epic|milestone>=<id> count=<n>`, run-dir paths, then commit the folder by name as `docs(plan): domain stories for <id>`. It fails → `domainStories.status=failed domainStories.reason=<why>`, with `reason=<why>` on the event.

Done when the target's `domainStories.status` is `ready` and its folder is committed, or `failed` with a reason.

## Dispatch

`podium launch <milestone>/<id>…` dispatches each ready story: a worktree on `story/<id>`, branched from the milestone `branch` into `<repo>-<id>` beside the repo, the story prompt below filled in, and the record (`status`, `attempts`, `agent`, `branch`, `worktrees`, `startedAt`, a `dispatched` event). One line per story:

- `LAUNCHED <id> paseo agent=… model=…`: a Paseo agent runs it in auto mode (dispatcher `paseo`).
- `PROMPT <file> model=<model>`: dispatcher `agent`. Start `Agent` with `run_in_background: true`, that model, and the file's text as the prompt; it works in the worktree by path. Record its task id: `podium set <milestone>/<id> agent.id=<task id>`.
- `SKIP <id> <why>`: not ready, nothing done. `FAILED <id> <why>`: nothing recorded and its worktree undone; fix what the line names, or ask the user.
- `DISPATCHER agent (podium dispatcher paseo to use Paseo)`: this machine had no dispatcher for the synced run, so launch used `agent`. Record the choice (SKILL.md, Dispatcher) before the next launch.

Story prompt (`launch` and the Podium's hand-off fill in its `<…>`; `<podium>` becomes the `podium` call with the run's `--dir`):

```
You build one story of an epic, alone, in this worktree, on branch story/<id>: <repo>: <path>, one per line.
Start with `<podium> brief <milestone>/<id>`: it prints your brief and every section of the plan the brief references, which is everything you need. A `MISSING <ref>` line names a reference it couldn't find: open that file yourself.
Log each step with `<podium> log <milestone>/<id> <STAGE> <note>`, which appends `<ISO time> <STAGE> <note>` to <podium dir>/stories/<milestone>/<id>.progress. STAGE is one of STARTED, RED (tests written and failing), GREEN, REFACTOR, FIX (when you start fixing something; note = `bug` or `test`, then what), CONTRACT (contract green), COMMITTED (note = sha), FAILED (note = why). The Podium shows where your time went from these lines, so log each step as it starts.
Work test-first: RED, GREEN, REFACTOR, then run the contract.
Write code that speaks for itself. Never name the story, milestone or decision ids (like <id>, M2, D7), the brief, the spec or any planning file in code, comments, test names, identifiers, log messages or docs: readers of the code have none of them. Default to no comments; add one only for a non-obvious external constraint, a third-party workaround, or a reason the code can't show.
Finish with one commit on story/<id> whose message ends with the trailer `Story: <id>`, log COMMITTED <sha>, and stop. Your final reply is one line: COMMITTED <sha>, or FAILED <why>.
Stay inside the brief's files in scope and on branch story/<id>. Never push; the orchestrator merges.
```

## Merge

`podium merge <milestone>/<id>… --land --next` merges each `story/<id>` in turn into its milestone's branch, in the worktree that has that branch checked out, runs the contract there, records the outcome and lands the story before the next id; a conflict or a red contract undoes that story's merge. The first result other than `MERGED` stops the queue with `STOPPED <id> <result>` and `PENDING <ids>`, the ids it never reached: act on that story's lines below, then queue the pending ids again. A contract runs for minutes, longer while other builds load the machine: run `merge` as a background `Bash` command with the longest timeout (2 hours), and act on each story's first word:

- **`CONFLICT <id> 1`** → tell its agent to rebase `story/<id>` onto the milestone branch, re-run the contract and log `COMMITTED <new sha>`. **`CONFLICT <id> 2`** → a failed attempt.
- **`RED`** → the merge is undone; a failed attempt, with the printed log tail as its reason.
- **`CONTRACT-CHANGED <digest> <repo>: <cmd>`** → nothing merged: a contract command this machine hasn't approved, new or changed by a pull. Show the user the command; only on their yes `podium approve <digest>` (`podium approve all` only on a yes to every line `podium approve` lists), then merge again.
- **`MERGED`** → `--land` **retires** the story (`podium land <milestone>/<id> --next` alone does the same for a story merged without it): it archives its Paseo workspace and agent, removes its worktree and releases a hand-off. With its milestone's `buildAll` on and that milestone's wave complete it launches the milestone's stories now ready: `LANDED <id>; launched <ids>`, then a line per `PROMPT` (Dispatch) or failure. `KEPT <path>: <why>` → that worktree has changes git won't drop: look at them before removing it. A subagent still running → `TaskStop`.

**Test services outlive their worktree.** When the repo's tests reuse containers or services per checkout (Testcontainers reuse, a docker compose project per worktree), nothing stops them when `land` removes the worktree, and every landed story leaves its set running until the machine slows and merges time out. Find how the repo scopes them (a label, a compose project name derived from the path) and, after each `LANDED`, stop the retired worktree's set. Never touch those of a checkout that still exists.

## Failed attempt

- **Attempt 1:** `podium launch <milestone>/<id> --retry @<file>`, the file holding the reason and the last 40 lines of its contract output: it retires the attempt, branches `story/<id>` afresh, puts the reason in the prompt and appends a `retry` event. `SKIP <id> KEPT …` → the worktree has changes: look, remove it, and launch again.
- **Attempt 2:** stop its agent (Paseo `archive_agent`, or `TaskStop`) and keep its worktree for fixing by hand. One `podium batch` with `<milestone>/<id> status=failed failure=… --event failed reason=…`, which also blocks every story that depends on it, and `. needsYou=<{reason: "<id> failed — retry, skip or fix by hand?", story}>`. Available → with its milestone's `buildAll` on, let the current wave finish, set that `buildAll` to `false` and ask the user in the terminal. Unavailable → keep building every story it doesn't block, and ask on `HUMAN available`.

Done when every story is `done`, or a failure has stopped the run and the user has been asked; either way, no story's agent is left running.
