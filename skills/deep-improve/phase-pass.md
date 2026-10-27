# The pass

Draft, test and preview a fix for each recurring finding, re-measure last week's token fixes, and leave one report. You review; a subagent per fix writes it. Nothing is pushed.

## 1. Collect and select

```bash
podium findings --all $(python3 ~/.claude/skills/deep-improve/scripts/improve.py remotes) > /tmp/deep-improve-findings.txt
python3 ~/.claude/skills/deep-improve/scripts/improve.py select < /tmp/deep-improve-findings.txt
```

`select` keeps open keys seen in ≥2 runs or of severity high, ranks them by runs × saving, then high severity, then runs, and prints `PICK <n> <key> ×<runs> <kind> <target> <repo> improve/<key> from <default>` up to the cap, `SKIP <key> — <why>` for the rest (a `repo:<name>` target, a skill not installed, a key still awaiting a decision in an earlier report, an `improve/<key>` branch that already exists, over the cap), and `REPORT <json>`. `EXISTS` → today's report was started: carry on from it, or rerun with `--force` when none of its worktrees exists yet. A line in the findings file other than `FINDING` (a remote that failed to fetch, `unknown command` from an older podium) goes into the report's Skipped section as a note; `podium` missing entirely → a report holding only that note, then step 6.

Done when `REPORT` is printed and every eligible finding is a `PICK` or a `SKIP`.

## 2. Draft each fix

Per `PICK`, set up the worktree yourself, then dispatch one subagent with the prompt below, all in parallel:

```bash
git -C <repo> fetch -q origin <default> && git -C <repo> worktree add -q -b improve/<key> <worktree> origin/<default>
```

(`<worktree>` from `improve.py entry <n>`.) A `tokens` finding also needs its **baseline**: run `podium tokens --since 7d` once per pass, take the `PATTERN` line this finding's title and moment name, and record it with `improve.py baseline <n> "<PATTERN line>"`. None matches → note in the entry "no baseline, not re-measurable".

The subagent prompt, filled in:

> Fix a recurring problem in `<repo>`, working only in the worktree `<worktree>` on branch `improve/<key>`. The finding: `<the FINDING line>`; fix type `<fix>`. Every recorded occurrence and its moment: `podium findings --all <remotes> --json`, entries with key `<key>`. Read each moment until you can name the cause.
>
> Make the smallest change that stops the recurrence, shaped by the fix type: `check` → a script, test or lint that catches it mechanically; `pointer` → one line where the agent needed the material, pointing at it; `standard` → a rule where the judgement is made; `delete` → remove the no-op or stale lines that caused it; `access` → the missing access or command; `script` → a script replacing the hand-run loop; `flag`, `brief`, `model`, `tool` → that setting, prompt, model choice or tool. A change to a skill follows the `writing-for-agents` skill and the repo's CLAUDE.md: steps end on a checkable criterion, and a one-off problem gets no always-on prose. Deleting is a valid fix. When no sound fix exists, change nothing.
>
> Commit once on the branch, message in the repo's style. Run the repo's test suite (its CLAUDE.md, README or CI config names the command); a failure that also fails on `origin/<default>` is pre-existing, say so. Never push. Reply with these lines only: `COMMIT <sha7> <subject>`, `PATHS <changed dirs, comma-separated>`, `TESTS <command> pass|fail|pre-existing <first failing line>`, `CHANGE <one line: what changed and why it stops the recurrence>`; or `NOFIX <why>`.

Done when every `PICK` has a reply.

## 3. Review each draft

Read `git -C <worktree> diff origin/<default>...HEAD`. A draft passes when the diff stays inside `PATHS`, addresses the cause the moments show, matches its fix type, and its tests pass or fail only as pre-existing. Otherwise send the subagent the problem once (`SendMessage`); a second miss, or `NOFIX` → `improve.py decide <n> failed "<why>"`, remove the worktree and branch (`git -C <repo> worktree remove --force <worktree>`, `git -C <repo> branch -D improve/<key>`), and list it under Skipped.

Done when every entry has passed review or is decided `failed`.

## 4. Re-measure last week's token fixes

`improve.py checks` prints `CHECK <date> <n> <key> since=<iso> baseline=~<tokens>/wk <kind> <pattern>` for each token fix pushed at least five days ago and not yet re-measured. Per line:

```bash
podium tokens --since <iso> | python3 ~/.claude/skills/deep-improve/scripts/improve.py compare <date> <n>
```

`KEPT` → goes under Re-measured. `REVERT` → `improve.py revert <date> <n>` adds a numbered entry and prints its `PICK`; set up its worktree as in step 2, then `git -C <worktree> revert --no-edit <sha>` and run the repo's tests yourself. A conflicting revert → `git -C <worktree> revert --abort`, then decide it `failed` as in step 3.

Done when `improve.py checks` prints nothing.

## 5. Preview each push

Per remaining entry:

```bash
~/.claude/skills/create-deep-pr/scripts/push-preview.sh <repo> origin improve/<key>:<default> --paths <PATHS>
```

A revert's `PATHS` are the dirs its commit touches. Done when every remaining entry has its preview output.

## 6. Write the report and notify

Write `~/.podium/improve/<date>.md` in the shape SKILL.md gives: the entries under the helper's numbers (gaps where a draft failed are fine), push previews verbatim. Then notify: on macOS `osascript -e 'display notification "<n> fixes drafted, <m> skipped" with title "deep-improve" subtitle "<report path>"'`; and end the run with the report path and one line per entry, `<n>. <key> — <change>`, closing on how to answer: `/deep-improve approve <n…>` or `reject <n…> [why]`.

Done when the report accounts for every `PICK`, `SKIP` and `CHECK` line of this pass, and the notification is sent.
