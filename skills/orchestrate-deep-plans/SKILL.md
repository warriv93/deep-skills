---
name: orchestrate-deep-plans
description: Plan a feature or product as epics with /deep-plan, break each milestone into stories, and build them in parallel, one agent per story, driven from the Podium, a live localhost dashboard; adopts a project already planned with /deep-plan. Use for "/orchestrate-deep-plans", "orchestrate this feature", a feature with several independent stories, or a half-done /deep-plan project.
argument-hint: <feature description, a milestone id, an Asana project or task link, join <ref> [--dir <repo>], or nothing to adopt>
---

# /orchestrate-deep-plans

A **project** holds **epics**. An epic is a product brief, or a theme that groups related runs. Its **milestones** are the `/deep-plan` runs that deliver it, and a milestone's **stories** are the user-story slices of its `tasks.md`. This skill plans the active milestone through deep-plan, breaks it into stories, dispatches one agent per story into its own worktree, merges each back, and hands the milestone to deep-plan's quality gate. The **Podium**, a live localhost dashboard, shows all of it and is where the user plans milestones and assigns stories.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

`join <ref>` in the arguments → join the run (Sync, below) first, since the checkout holds no run yet. Start every turn with `podium turn`, act on its lines, then read deep-plan's ledger of each milestone being planned or built (`.deep-plan/state.md` in the worktree of its branch) and resume. It first updates this skill and the `podium` tool (`UPDATED skills` with `RELOAD skills`: tell the user in one line that the skill updated and the changes apply from their next session; `UPDATED podium` with `RESTART server`: tell them to press Restart in the Podium; `WARN`: mention it once; `SKIP` needs nothing), then prints `RECUR <key> ×<runs> — <title>` for each open finding seen in several runs (Phase 5): list them to the user in one message. Then it pulls what another machine or person saved (_sync_, below; `PULLED`: the run moved elsewhere), fetches the repo, fast-forwards the base branch when it is cleanly behind origin (`BEHIND` says why it wasn't), records each milestone that landed elsewhere as `done` with its stories' commits (`LANDED`: say in one line what moved or landed; `SKIP-LANDED`: another person's milestone, left to them), and prints the status, the user's mode, whether the Podium is up, Asana's changes, and the requests queued since it last ran. `ACT` lines are the user's own answers (`confirm` and `reverse` settle assumptions, `asana` maps a link, `asana-done` answers a milestone done in Asana, `asana-complete` completes a landed milestone's subtask): apply them in any turn. `LIST` lines are other queued requests: report them, and act on `LIST share` (Share, below). The turn is done when every `ACT` line is applied. `.deep-plan/` holds deep-plan history but no `podium/podium.json` → Phase 0. `podium turn` answers `unknown command 'turn'` → the run predates the `podium` tool and has no `orchestrator` block: register it (`podium`, below), switch its sync on with `podium sync on --ref refs/heads/podium` (its state is on that branch), and turn again.

**Map first, work on a start.** The run never starts a milestone by itself, whatever the user's mode. A bare `/orchestrate-deep-plans` only maps: sync, adopt or reconcile `podium.json` (Phase 0 when there is none), start the Podium and the watcher, and report in one message the Podium link, what is active, done, draft, parked and later, what waits on the user, the `LIST` requests, and the **next milestone** you suggest with one line of why (never a `moved` one; a milestone another is waiting for that hasn't landed first, then a `grilled` one, else the first in run order whose deps have landed, a dep on a `moved` milestone meaning its `movedTo` target), started with its Plan button or `/orchestrate-deep-plans <id>`. Then end the turn. Work starts only on a **start**: a Podium request that arrives while the watcher runs (plan, assign, build all), or the user naming the work, e.g. `/orchestrate-deep-plans M2` or a feature to plan. A milestone already mid-build resumes its merges and running agents, and dispatches nothing new.

**Waiting for another milestone.** Planning, or anything else, concludes that milestone M12 is better done after M10, which deps don't say → `podium set milestone:M12 'waitsFor=[{"milestone":"M10","reason":"<one line>"}]' waitsForAck=false --event status text="M12 waits for M10: <reason>"`, and raise it once in chat: "M12's planning recommends doing M10 first: <reason>; go ahead with mocks, plan M10, or park M12?". The relation is a soft one: deps stay the hard relation, and building on with mocks is always allowed. `REQUEST proceed <id>`, `LIST proceed <id>` or the user saying go ahead → `podium set milestone:<id> waitsForAck=true` and carry on, mocking what the other milestone would provide; the same command resets the ack when `waitsFor` changes. While M12 waits and isn't acked, `land --next` holds its next wave and prints `WAITING M12 for M10`; a `podium launch` still works and notes it.

## Run state — `.deep-plan/`

deep-plan's ledger and files stay deep-plan's. This skill keeps its own files in the run dir's `podium/` folder, and the epics' and milestones' domain stories in `domain-stories/`; paths below, and every path inside `podium.json`, are relative to the run dir:

| File | Written by |
| --- | --- |
| `podium/podium.json` | the orchestrator (this session) |
| `podium/events.jsonl` | the orchestrator, append-only |
| `podium/requests.jsonl` | the Podium server, append-only |
| `podium/handoffs.json` | the Podium server, from its copy button |
| `podium/watcher.json` | the watcher, its heartbeat; the Podium refuses requests without it |
| `podium/stories/<milestone>/<id>.md` — the story's **brief** | the orchestrator, through `podium breakdown` |
| `podium/handoffs/<milestone>-<plan, ahead, gate or retro>.md` — a planning, gate or retro subagent's prompt | the orchestrator, through `podium handoff` |
| `podium/stories/<milestone>/<id>.prompt` — its story prompt, for a subagent | the orchestrator, at dispatch |
| `podium/stories/<milestone>/<id>.progress` | that story's agent, append-only, through `podium log` |
| `domain-stories/<epic or milestone>/`, committed: per story `<Title>.story.json` and `<Title>.egn.svg` | that epic's or milestone's drawing subagent |

**Single writer:** every file has exactly one writer, so parallel agents never race.

**Sync:** the run state is committed to a ref on origin and pushed, so the run carries on from another machine and two people can share it. It is on for every run: a new run's ref is `refs/heads/podium-run/<repo>`; a run from before the `podium` tool keeps its `refs/heads/podium` branch. Code commits never carry it, and it never touches the working tree or the current branch. Remote, ref and on/off are each machine's own. A second machine or person **joins** with `/orchestrate-deep-plans join <ref> [--dir <repo>]` in a clone of the run's repo (`--dir`, else the cwd's): `podium --dir <repo>/.deep-plan sync on --ref <ref>`, the ref `podium sync status` prints where the run started, then `podium sync pull`; no `init`, since the registration travels with the run. Then map as a bare `/orchestrate-deep-plans` does. Every command that appends a major event (the spec, architecture and build checkpoints, a grill, the merge that completes a wave, a failure, a landing, settled assumptions, a milestone's status or owner) saves and pushes on its own; a big change without one, such as an adoption, gets `podium sync save "<what changed>"`. Sync merges, never overwrites: `podium.json` key by key, events and progress lines as their union; a text file both sides changed keeps yours, writes theirs beside it as `<file>.remote` and adds to your `needsYou`. `podium turn` pulls first. Pushes never wait for the user. `SAVED … (not pushed: …)` → the next save pushes it; `BEHIND` → `podium sync pull`; `KEPT the watcher is running` → nothing to do: the watcher pulls every minute, merging with unsaved changes.

**Share**, on `REQUEST share` or `LIST share` (the Podium's Share button) or the user asking to share: sync off on this machine (`podium sync status` doesn't start `ref <ref> ON`) → `podium sync on` and `podium sync save shared`; otherwise only reply. Reply in chat with the colleague's steps, the ones the Share button's tooltip lists (`SHARE_STEPS` in [`podium_ext.py`](podium_ext.py)), `<ref>` filled in and `<url>` what `git remote get-url origin` prints:

1. Clone this run's repo if you haven't: `git clone <url>`.
2. Install the podium tool (`pip3 install --user git+https://github.com/warriv93/podium-dashboard`) and the orchestrate-deep-plans skill (clone https://github.com/warriv93/deep-skills and run its `./install.sh`; see its README).
3. In your clone, start `claude` and run `/orchestrate-deep-plans join <ref>`.
4. Claim a milestone: `podium claim <id>`.

Done when the reply holds all four steps with the real ref and URL.

**Owner:** each milestone has one, `milestones[].owner`, the person (`podium whoami`) who plans and builds it, so two people sharing a run never work on the same milestone. Claim a milestone before planning it (`podium claim <id>`: it pulls, then pushes the claim at once); `launch` claims an unowned one for you. `launch`, `merge`, `land` and `turn`'s landings refuse a milestone someone else owns (`owned by <who>`): tell the user; take it over (`podium claim <id> --force`, or `--force` on the verb) only when they say so. Each person keeps their own `active`, `needsYou` and assumptions in `people.<you>`; `set .` and `status` handle that.

**Contracts:** this machine runs a contract command only once it approved that exact text, so a pull never runs someone else's command unseen: `merge` stops on `CONTRACT-CHANGED` (phase-3-build.md, Merge), and you approve only the contract commands you wrote yourself, by digest (phase-2-breakdown.md, Contract).

**`podium`** is the command of the [podium-dashboard](https://github.com/warriv93/podium-dashboard) tool (README, Install); this skill's verbs come from its extension, [`podium_ext.py`](podium_ext.py). A run registers once, then switches sync on:

```sh
podium init --name orchestrate-deep-plans --command /orchestrate-deep-plans --extension ~/.claude/skills/orchestrate-deep-plans/podium_ext.py --phases recon,spec,mock,architecture,stories,build,gate,verify,land
podium sync on
```

It finds `.deep-plan/` from the cwd; elsewhere give `--dir <repo>/.deep-plan` first. `podium server` and `podium watch` run the Podium's server and watcher. Run bare, it lists its commands, the extension's included. It is the orchestrator's only way into `podium.json` and `events.jsonl`: `turn` to start a turn, `status` and `get` to read, `set` to change and `batch` for several sets in one write (one `set` argument line per op on stdin), `claim` and `release` for owners, `breakdown` to turn a milestone's `tasks.md` into stories and briefs, `launch`, `merge` and `land` to build a story, `peek` to check on one, `handoff` for the prompt that passes planning, the quality gate or a retro to a subagent, `commits` and `backfill` for git, `prs` for pull-request state, `sync` for sync, `asana refresh` for Asana. It writes atomically and keeps the file, which grows to hundreds of kilobytes, out of context. Give every change a person would want to see an `--event`.

The tool's [`sample/`](https://github.com/warriv93/podium-dashboard/tree/main/sample) is the reference run: copy the shapes of `podium/podium.json`, `podium/events.jsonl` and `podium/stories/*` from it. Field values:

- `epics[]`: `id`, `title`, `summary`, `spec` (its brief, if any), `milestones`, `uncovered`, `domainStories`. Milestone ids are unique across the project.
- `active`: `{epic, milestone}` for the milestone being planned or built, or `null`. A bare story id and `milestone:` mean this one; a second milestone building beside it is `milestone:<id>`, its stories `<milestone>/<id>` (Running two milestones at once).
- `milestones[].buildAll`: that milestone's Build all is on, so `podium land --next` launches its next wave. A top-level `buildAll`, from an older run, is the active milestone's; `podium` moves it there.
- `milestones[].status`: `done` `working` `todo` `draft` `parked` `later` `dropped` `moved`. A `moved` milestone was folded into `movedTo` by the cut ([milestone-cut.md](milestone-cut.md)): it is never suggested, planned or landed, and a wait on it is a wait on the milestone its moves end in.
- `milestones[].cut`: `{pattern, valuable, kept?}`, how the cut made it.
- `decisions[]`: `{id, epic, question, type, affects, blockedBy, status, owner?, outcome?, missing?}`, an epic-wide question settled before its cut ([milestone-cut.md](milestone-cut.md), Epic decisions). `status`: `open` `resolved` `out-of-scope` `invalidated`; `type`: `discussion` `research` `prototype` `unblock`; `owner` claims it like a milestone's.
- `milestones[].grilled`: when its questions were answered while another milestone was active; it is the suggested next milestone once that one lands.
- `milestones[].phase`: `recon` `spec` `mock` `architecture` `stories` `build` `gate` `verify` `land`.
- `stories[].status`: `todo` `working` `approval` `done` `failed` `blocked` `dropped`. The Podium derives ready / waiting from `deps`.
- `deps`: ids it is blocked by (milestones among milestones, stories within a milestone). `stories[].overlapAfter`: ids it shares files with, which must merge first.
- `needsYou`: `{reason, story?}` while the run waits on the user, otherwise `null`; `story` is `<milestone>/<id>` for a story of a milestone other than the active one.
- `milestones[].pr`: `{number, url, state}` once its PR is open; `state` is `draft` `open` `merged` `closed`.
- `mock` (an epic's or a milestone's): `{path, url}` of its UI mock. `path` is relative to the run dir, which the Podium hosts (`../` reaches the repo, hosted under `/repo/`); `url` is a published copy, such as a claude.ai artifact. A milestone artifact with `phase: "mock"` counts as its mock. The Podium shows a 🎨 link on the card, the page title and the sheet.
- `domainStories` (an epic's or a milestone's): `{status, at, stories: [{title, path, spec}], questions, reason}`, `status` one of `drawing` `ready` `failed`; `path` is the story's `.egn.svg`, `spec` its JSON, `questions` the open-questions file, `reason` why it failed. The Podium's Story button on the epic or milestone opens them over the map.
- `asana` (the project's, an epic's or a milestone's): the Asana project, task or subtask it is linked to, shaped as in [asana.md](asana.md). The Podium shows an Asana link, the assignee and custom fields, and asks whether to skip a milestone whose subtask is done in Asana but hasn't landed.
- Progress lines: `<ISO time> <STAGE> <note>`, STAGE one of `STARTED` `RED` `GREEN` `REFACTOR` `FIX` `CONTRACT` `COMMITTED` `FAILED`; a `FIX` note starts with `bug` or `test`. A finished story's sheet shows where its time went, each stretch counted toward the step its line began.

## Podium

- **Start:** run `podium server --detach`. It prints its URL (port 8765, or the next free one) and keeps serving outside the session, so no background-task limit stops it; it stops itself after an hour with no one at a Podium tab (in view and used in the last 10 minutes), no button pressed and no change to the run (`--idle <minutes>`, its log in `server.log`). It also lists the orchestrator's files in the clone's `.git/info/exclude`: tracked on a code branch they would swap with every branch switch, so sync carries them instead. Record `podium: <url>` in the ledger and give the user the link: the URL in your reply, with a sentence on what it shows (the pipeline stepper; the epic, milestone and story maps with live status; the activity feed; the buttons to plan a milestone, assign stories, build all or draw an epic or milestone as domain stories; the Available/Away toggle). **Open it in Paseo's browser** when its MCP tools are available: `browser_list_tabs`; a tab already on the URL → leave it; otherwise `browser_new_tab` with the URL, then check its title with `browser_evaluate`. A `browser_timeout` can still open the tab, so list the tabs again before retrying. A tab whose title isn't the Podium's (Paseo's agent-opened tabs can fail to reach local servers) → `browser_close_tab` it. No working tab, or no Paseo → the link is enough.
- **Resume:** `PODIUM down` in the turn → start it again; `not watching` → start the watcher.
- **Watch:** run `podium watch` (add `--paseo <paseo binary>` when Paseo dispatches) under the `Monitor` tool with the longest `timeout_ms` (30 minutes). Each line it prints arrives as an event to act on ([phase-3-build.md](phase-3-build.md) says how) while it keeps watching. When the monitor expires, arm it again: it resumes where the last one stopped, so nothing is lost in between. It ends itself with `LAPSE` once the user isn't available and no story is working, since only the user at this computer could press a Podium button then: let it rest; the next `/orchestrate-deep-plans` starts it again.

## The human

The user is **available**, **mobile** or **unavailable**; `podium human` says which and until when. Their hours decide (`podium hours`, `Mon-Fri 07:00-17:00` by default, local time) unless the Podium's toggle overrides them until the next change of hours. Both are one per machine, in `~/.podium/human.json`: a flip in any Podium holds for every run, so each watcher prints it. A Podium tab in use turns Mobile into Available on its own once Mobile has held 15 minutes, since the Podium only answers on this computer. The user invoking `/orchestrate-deep-plans` themselves makes them available for the session, whatever their hours: flip the toggle to `available`, unless it says `mobile` (they invoked it from the phone) (a watcher event or an agent finishing is not an invocation). The user says in the terminal they're leaving, on their phone or back → flip the toggle for them: `curl -s -X POST <podium>/human/<unavailable|mobile|available|auto>`, plus `?until=HH:MM` for another end. The watcher prints `HUMAN <mode>` on every flip; append a `human` event (`set . --event human mode=<mode>`).

- **Available:** ask as each phase says.
- **Mobile:** the user reads and answers this chat on their phone and can't open localhost: the Podium, a mock it hosts, the app under test. Ask only what blocks the run or can't be undone, in as few questions as the decision allows; everything else becomes an assumption as when unavailable, put to them when they're back at a desk (`HUMAN available`). Show, don't link: when a step changes something they'd look at (a mock iteration, a UI story, a verify screenshot), take a screenshot with headless Playwright and Read the PNG in the turn that reports it, so the image sits in the conversation, with the mock's published `url` when it has one. Podium links are no use there.
- **Unavailable:** keep the run moving on your own judgement. Every question a phase or deep-plan would put to the user, sign-off gates and the grill included, becomes an **assumption**: take the option you'd recommend, record it with `podium assume "<question>" "<choice>" "<why>" --short "<the decision in a few words>" [--story <id>]`, and carry on.
- **Landing:** a milestone that passes verify merges into the base locally (deep-plan Phase 6), with no PR unless the user asked for one. While unavailable, merge is the assumed answer to the debrief, unless a success criterion still needs the user (checked on a device, say): then set `needsYou` and wait.
- **Waits for the user either way:** everything that leaves the machine or can't be undone, apart from sync's pushes, a retro's findings (Phase 5) and completing a landed milestone's Asana subtask ([asana.md](asana.md)): pushing, opening or readying a PR, deleting. Set `needsYou` for it and go on with the work that doesn't depend on it; when none is left, wait for `HUMAN available`.
- **`HUMAN available`:** name the milestones merged since they left, run `podium prs` and link any open PRs, and put the open assumptions (`podium assumptions`) to the user in `AskUserQuestion` rounds, your choice as the recommended option; the Podium's Confirm and Reverse buttons answer them too (`REQUEST confirm|reverse <n>`). Settle them with `podium settle <n>[,<n>…] <confirmed|reversed>`, numbered as `assumptions` prints them (`t<n>` for one from before the run kept assumptions per person). A reversal is rework: amend the planning file it touched, and send a story it shaped back to `todo` with the answer in its brief.

## Milestone cut

Read [milestone-cut.md](milestone-cut.md) when an epic gets its milestones, when deep-plan reports `TOO BIG <milestone>: <why>`, and when it reports `OPEN DECISION <question>: affects <milestones>`; it settles the epic's decisions before the cut.

## Asana

Read [asana.md](asana.md) on an Asana link, in the arguments or as `REQUEST asana`, and while `podium.json` holds an `asana` link: at sync, when a linked milestone's `phase` changes, when one is planned and when one lands.

## Dispatcher

Paseo when its CLI runs (`paseo --version`); otherwise background `Agent` subagents working in the story's worktree. Record the choice with `podium dispatcher paseo` or `podium dispatcher agent`; it stays on this machine, so a pull never changes it. `podium launch` dispatches through it (phase-3-build.md, Dispatch). Every spawn in this skill, stories included, follows deep-plan's _subagent protocol_ ([../deep-plan/subagent-protocol.md](../deep-plan/subagent-protocol.md)): read it before the run's first spawn.

## Running two milestones at once

A second milestone can build beside the active one when the two change different files, or when they share files and the user accepts the conflicts its merge into the base may bring. A new milestone that moves or rewrites code the other is building → before either dispatches another story, ask the user whether the other should wait.

- **Its own worktree:** the second milestone builds in its planning worktree, `../<repo>-plan-<id>` (phase-1-plan.md, Planning ahead), which keeps its branch, ledger, planning files and contract; `merge` merges into the worktree that has the milestone's branch checked out. `brief` resolves paths from the main checkout's `.deep-plan/`, so record its `spec` and `artifacts`, and reference its planning files in its briefs, by absolute path.
- **Story ids** are unique across both: watcher events, story worktrees (`<repo>-<id>`) and `story/<id>` carry the bare id, so the second milestone's stories take a prefix of their own at breakdown (`W1`–`W11` beside `S1`–`S13`).
- **Commands** name its stories `<milestone>/<id>` (`launch`, `merge`, `land`, `brief`, `set`, `assume --story`) and the milestone `milestone:<id>`; `podium ready --milestone <id>` lists its ready stories, and `podium status` shows both milestones.
- **Build all** is per milestone: each has its own `buildAll` and waves, and the Podium's Build all and Stop buttons sit on one milestone (`REQUEST build-all <milestone>`, `REQUEST stop <milestone>`).
- **Load:** both milestones' builds share this machine, so every contract run slows: `merge` runs in the background (phase-3-build.md, Merge).
- **Landing:** when one lands, `turn` sets `active: null`; point `active` at the one still building.

## Phases

Run in order. On entering a phase, read its file:

| Phase | File | Done when |
| --- | --- | --- |
| 0 (adopting only) | [phase-0-adopt.md](phase-0-adopt.md) | every run in an epic in `podium.json`, history backfilled; the user has the link |
| 1 | [phase-1-plan.md](phase-1-plan.md) | the active milestone reached deep-plan's Phase 2 checkpoint; Podium live |
| 2 | [phase-2-breakdown.md](phase-2-breakdown.md) | every story has a brief, deps, files and model; the user has the Podium link |
| 3 | [phase-3-build.md](phase-3-build.md) | every story merged with the contract green, or the run stopped on a failure and the user was asked |
| 4 | [phase-4-handback.md](phase-4-handback.md) | deep-plan's quality gate, verify and landing done; the milestone `done` |
| 5 | [phase-5-retro.md](phase-5-retro.md) | the landed milestone's friction recorded as findings, or none to record; the next milestone suggested |
