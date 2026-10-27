# deep-skills

These skills extend [podium-dashboard](https://github.com/warriv93/podium-dashboard).

[Claude Code](https://claude.com/claude-code) skills for planning and building features and apps: `/deep-plan`, `/orchestrate-deep-plans`, `/deep-app-plan`, `/deep-qa`, `/create-deep-pr`, `/deep-improve` and `/discuss`.

## Quick start

To run `/orchestrate-deep-plans`:

1. Have [Claude Code](https://claude.com/claude-code), `python3`, `git`, `curl` and `gh` (logged in) on your PATH, and a git repo whose `origin` you can write to.
2. Install the Podium: `pip3 install --user git+https://github.com/warriv93/podium-dashboard`. Check `podium` runs.
3. Install the skills: `git clone https://github.com/warriv93/deep-skills.git && cd deep-skills && ./install.sh`, then start a fresh Claude Code session.
4. In your repo, run `claude`, then `/orchestrate-deep-plans <feature description>`. The Podium opens on localhost.

`/deep-plan`, which it calls, uses the other skills listed under Dependencies when they're installed and works without them.

## Skills

| Skill | What it does |
| --- | --- |
| [`/deep-plan`](skills/deep-plan/README.md) | Builds one feature into an existing codebase: recon, **grill** to lock the spec, a throwaway clickable **mock** for UI work, deep-modular architecture, SDD+TDD slices (one commit per green slice), two code-review gates, a looping verification + security gate, and a human-in-the-loop debrief. Phase instructions load on demand. |
| [`/orchestrate-deep-plans`](skills/orchestrate-deep-plans/README.md) | Plans a feature or product as **epics** of **milestones** through `/deep-plan` (or adopts a project already planned with it), breaks the active milestone into **stories** with explicit dependencies, and builds them in parallel, one agent per story in its own worktree (Paseo, or Claude subagents), merging each back under the contract. Each new epic first settles its epic-wide questions with you, then is cut into milestones a user can notice, with one sign-off on the cut before any is planned. A live localhost dashboard, the **Podium**, shows the pipeline, an epic map, a milestone map per epic that drills into each milestone's story map, progress, quality and activity, and lets you plan a milestone, assign stories, build them all, or draw an epic as domain stories (the Domain story button needs the `deep-domain-storytelling` skill installed separately; optional). It knows your working hours (or the Podium's Available/Away toggle): while you're away it keeps going, decides what it would have asked you, and puts those decisions to you when you're back. The run state syncs through git, apart from the code, merging rather than overwriting, so the run carries on from another machine and two people can share it, each building the milestones they claimed. The Podium and its `podium` command come from the [podium-dashboard](https://github.com/warriv93/podium-dashboard) tool; this skill adds its orchestration verbs as an extension. |
| [`/deep-app-plan`](skills/deep-app-plan/README.md) | Builds a whole app from nothing: product frame, one-way platform decisions, scaffold + CI, an M0 walking skeleton live in prod, then each milestone through `/deep-plan`, ending on a launch-readiness checklist. |
| [`/deep-qa`](skills/deep-qa/README.md) | QAs a change through **lenses** picked by what the diff touches: defects and spec (`code-review`), design (strategic programming: shallow modules, leaking information, bolted-on special cases), security, the contract, P1 journeys in the real app, accessibility (axe-core, keyboard, reflow) and performance. Writes one findings file with a verdict, `pass`, `fixable` or `blocked`, and fixes nothing: the caller does. |
| [`/create-deep-pr`](skills/create-deep-pr/README.md) | Takes finished work to a **draft** PR (`--ready` for a ready one): branch named like the repo's recent ones, commits in its style, runs the checks its CI would fail on, previews the push (commits, files, suspicious files) before it goes, screenshots UI changes with Playwright and posts them through a `pr-screenshots` orphan branch, writes the body like the repo's recent merged PRs and requests a Copilot review. |
| [`/deep-improve`](skills/deep-improve/SKILL.md) | The weekly improvement pass over the **findings** orchestrator runs record: picks the open ones that recur (≥2 runs, or high severity), has a subagent draft each fix in its own worktree on `improve/<key>`, runs the repo's tests, re-measures last week's token fixes (no drop → a drafted revert), and writes a numbered report in `~/.podium/improve/` with each push preview. `/deep-improve approve <n…>` or `reject <n…>` then pushes, after your yes per push, or records the finding as won't fix. Never pushes on its own. |
| [`/discuss`](skills/discuss/SKILL.md) | A whiteboard session about a topic: grounded points, a recommendation with its tradeoffs, sketches under `/tmp`, and nothing built. Ends on a decision record of what was settled and what's still open. |

## Layout

Each skill is a folder: `skills/<name>/SKILL.md` is the entry point (frontmatter + phase router) and the sibling `phase-*.md` files are read only when the agent enters that phase. Links between them are relative, so the folder works wherever it is linked from.

## Install (symlink — live editing)

```bash
git clone https://github.com/warriv93/deep-skills.git
cd deep-skills
./install.sh
```

`install.sh` symlinks every `skills/<name>/` folder to `~/.claude/skills/<name>` (idempotent). Edits in the repo are live immediately. A name that already exists there and points elsewhere is kept, so a machine-specific skill of the same name wins.

**Antigravity / Gemini:** if `~/.gemini/config/` exists, `install.sh` also links the skills into `~/.gemini/config/skills/`, together with [`claude-tool-map`](gemini/claude-tool-map/SKILL.md), which translates the Claude Code tools, model tiers and slash commands the skills mention into their Antigravity equivalents. Each skill tells a non-Claude agent to load it first.

## Editing

- **Body or phase-file change** → picked up the next time the skill runs.
- **New skill, or a changed `description:`** → start a fresh Claude Code session so it's re-discovered.

Skill writing follows the [`writing-for-agents`](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents) reference; [CLAUDE.md](CLAUDE.md) tells Claude to load it and lists this repo's conventions.

## Creating a new skill

1. Create `skills/<name>/SKILL.md`:

   ```markdown
   ---
   name: <name>
   description: <What it does, leading word first>. Use for "/<name>", <each distinct trigger>.
   argument-hint: <what to type after the command>
   ---

   # /<name>

   <steps, each ending on a completion criterion>
   ```

   For a skill only you fire by hand, add `disable-model-invocation: true` and make the description a one-line human summary; it then costs no context.

2. `./install.sh`, restart the session, type `/<name>`.

## Dependencies

- **`/deep-plan`** calls `/deep-qa` for its gates. It also uses these when present: `speckit-custom-plan-tdd-sdd` (else `/to-spec` and `/to-tickets`, or inline steps), `/wayfinder`, `/grill-with-docs`, `/research`, `/prototype`, `frontend-design`, `dataviz`, `/codebase-design`, `/setup-pre-commit`, `git-guardrails-claude-code`, `/tdd`, `/security-review`, `/run`, `/diagnosing-bugs`, `/to-spec`, `/to-tickets`, and `/create-deep-pr` when the user asks for a PR.
- **`/orchestrate-deep-plans`** calls `/deep-plan` and follows its subagent protocol (`skills/deep-plan/subagent-protocol.md`), and dispatches through Paseo's MCP tools when present (`Agent` subagents otherwise). Its Podium is the `podium` command of [podium-dashboard](https://github.com/warriv93/podium-dashboard) (`pip3 install --user git+https://github.com/warriv93/podium-dashboard`), which needs only `python3`; its run state syncs to `refs/heads/podium-run/<repo>` on origin, so `origin` needs write access; a milestone's retro pushes findings to your findings remote (`"findings"` in `~/.podium/improve.json`; without one findings stay local), so that needs write access too. Its domain-story button calls `deep-domain-storytelling`, which is optional and installed separately.
- **`/deep-app-plan`** calls `/deep-plan`, plus `/grilling`, `/domain-modeling`, `/writing-for-agents` and `/security-review`.
- **`/deep-qa`** calls `code-review` (Matt Pocock's dual-axis) and `/security-review`, and uses `/codebase-design`, `/run` and `/web-perf` when present. Its accessibility script needs `node`; it installs Playwright and `@axe-core/playwright` into `~/.cache/axe-playwright` on first run.
- **`/deep-improve`** needs the `podium` command of [podium-dashboard](https://github.com/warriv93/podium-dashboard) with its `findings` and `tokens` verbs, read access to your findings remotes (the `"findings"` list in `~/.podium/improve.json`; without one it has nothing to read) and write access to the repos it fixes, plus `python3`. It previews pushes with `/create-deep-pr`'s `scripts/push-preview.sh` and follows `writing-for-agents` for skill fixes. A weekly Paseo schedule running `/deep-improve` is optional; any scheduler that starts a Claude Code session works.
- **`/create-deep-pr`** needs `gh`, logged in. Screenshots use the Playwright MCP tools when present.
