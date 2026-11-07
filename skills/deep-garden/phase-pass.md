# The pass

Find each repo's hotspots, survey them for candidates, draft and test the best few on their own branches, and leave one report. You review; a subagent per repo surveys and a subagent per candidate drafts. Nothing is pushed.

## 1. Pick the repos

```bash
podium findings --all $(python3 ~/.claude/skills/deep-improve/scripts/improve.py remotes) > /tmp/deep-garden-findings.txt
python3 ~/.claude/skills/deep-garden/scripts/garden.py repos --findings /tmp/deep-garden-findings.txt
```

`REPO <default> <design runs> <path>` per repo to garden, the ones whose milestones' quality gates keep reporting Design rows (the orchestrators' `design-<repo>` findings) first; `SKIP <path> — <why>` for the rest. `podium` missing or failing → an empty findings file and a note under Skipped; the pass goes on.

Done when every repo is a `REPO` or a `SKIP`.

## 2. Measure each repo

Per `REPO`, after `git -C <path> fetch -q origin <default>`:

```bash
python3 ~/.claude/skills/deep-garden/scripts/garden.py hotspots <path>
python3 ~/.claude/skills/deep-garden/scripts/garden.py dupes <path>
```

`HOT <score> ×<churn> <lines>L <file>`, highest first; `DUPE <lines>L <a>:<s>-<e> <b>:<s>-<e>` from jscpd or PMD CPD, or `NODUPE <why>` (goes under Skipped once per pass). No `HOT` line → skip the repo: none of its code changed.

Done when every remaining repo has its `HOT` lines and a `DUPE` or `NODUPE` line.

## 3. Survey each repo

One subagent per repo, all in parallel, with this prompt filled in:

> Survey `<path>` for deepening refactors, read-only. Read `~/.agents/skills/improve-codebase-architecture/SKILL.md` and do its step 1, Explore, taking these as the direction the user named: the hotspots `<HOT lines>`, the duplication `<DUPE lines>`[, and `<design runs>` milestones whose quality gate flagged design problems]. Use the vocabulary of `~/.agents/skills/codebase-design/SKILL.md` and apply its deletion test to every suspect. Stop after step 1: no HTML report, no questions. A candidate that contradicts an ADR in `docs/adr/` or matches a line in `<rejected file>` is out.
>
> Keep candidates a reviewer can read in one sitting: one seam, behaviour unchanged, the existing tests as the safety net. Reply with at most `<cap + 2>` lines `CANDIDATE <kebab-slug> <Strong|Worth-exploring|Speculative> <file,file,…> — <one-line title>`, best first, then `QUESTION <one line>` for anything you would have asked; or `NONE <why>`.

`<rejected file>` is `<path>/.deep-plan/garden-rejected.md`. `improve-codebase-architecture` not installed → drop its sentence and have the subagent explore the hotspots with `codebase-design`'s deletion test alone, noting it in Questions; neither installed → the survey works from the hotspots and duplication alone. Each `QUESTION` goes to the report's Questions section.

Done when every repo has a reply.

## 4. Select

Write each repo's `REPO` line from step 1 followed by its reply into `/tmp/deep-garden-candidates.txt`, then:

```bash
python3 ~/.claude/skills/deep-garden/scripts/garden.py select < /tmp/deep-garden-candidates.txt
```

`select` ranks each repo's candidates by strength, then by the hotspot score of their files, and prints `PICK <n> <slug> <strength> <branch> from <default> team|solo in <path>` up to the cap per repo, `SKIP <slug> — <why>, in <path>` for the rest (rejected before, awaiting a decision in an earlier report, branch already exists, over the cap), `BAD <line>` for a reply line it couldn't read, and `REPORT <json>`. `EXISTS` → this month's report was started: carry on from it, or rerun with `--force` when none of its worktrees exists yet. `team` means more than one author committed in the last 90 days.

Done when `REPORT` is printed and every candidate is a `PICK`, `SKIP` or `BAD`.

## 5. Draft each refactor

Per `PICK`, set up the worktree yourself (`<worktree>` from `garden.py entry <n>`), then dispatch one subagent with the prompt below, all in parallel:

```bash
git -C <path> worktree add -q -b <branch> <worktree> origin/<default>
```

> Refactor `<path>`, working only in the worktree `<worktree>` on branch `<branch>`. The candidate: `<CANDIDATE line>`. Read `~/.agents/skills/codebase-design/SKILL.md` for the vocabulary, and the repo's CLAUDE.md or AGENTS.md for its conventions.
>
> Deepen that one seam and nothing else. Every commit is structural: behaviour stays the same, the existing tests stay as they are apart from following moved or renamed code, and no feature, fix or formatting sweep rides along. Commit in the repo's style. Find the test command in its CLAUDE.md, README, CI config or `.deep-plan/contract.cmds`, and run it; a failure that also fails on `origin/<default>` is pre-existing, say so. When the refactor can't stay structural or the tests can't pass, revert to `origin/<default>` and stop. Never push. Reply with these lines only: `COMMIT <sha7> <subject>`, `PATHS <changed dirs, comma-separated>`, `TESTS <command> pass|fail|pre-existing <first failing line>`, `CHANGE <one line: what got deeper, and the deletion test it now passes>`; or `NOFIX <why>`.

Done when every `PICK` has a reply.

## 6. Review each draft

Read `git -C <worktree> diff origin/<default>...HEAD`. A draft passes when the diff stays inside `PATHS` and the candidate's files, every commit is structural (no assertion or expected value in a test changed, no new behaviour), and its tests pass or fail only as pre-existing. Otherwise send the subagent the problem once (`SendMessage`); a second miss, or `NOFIX` → `garden.py decide <n> failed "<why>"`, remove the worktree and branch (`git -C <path> worktree remove --force <worktree>`, `git -C <path> branch -D <branch>`), and list it under Skipped.

Done when every entry has passed review or is decided `failed`.

## 7. Preview each push

Per remaining entry, `solo` previews the push to the default branch and `team` the branch a PR would come from:

```bash
~/.claude/skills/create-deep-pr/scripts/push-preview.sh <path> origin <branch>:<default> --paths <PATHS>   # solo
~/.claude/skills/create-deep-pr/scripts/push-preview.sh <path> origin <branch> --paths <PATHS>             # team
```

Done when every remaining entry has its preview output.

## 8. Write the report and notify

Write `~/.podium/garden/<date>.md` in the shape SKILL.md gives: the entries under the helper's numbers (gaps where a draft failed are fine), push previews verbatim. Then notify: on macOS `osascript -e 'display notification "<n> refactors drafted, <m> skipped" with title "deep-garden" subtitle "<report path>"'`; and end the run with the report path and one line per entry, `<n>. <repo> · <slug> — <change>`, closing on how to answer: `/deep-garden approve <n…>` or `reject <n…> [why]`.

Done when the report accounts for every `REPO`, `SKIP`, `PICK`, `BAD` and `QUESTION` line of this pass, and the notification is sent.
