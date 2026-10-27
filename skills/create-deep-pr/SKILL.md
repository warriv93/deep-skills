---
name: create-deep-pr
description: Take finished work to a draft pull request: branch, commit, run the checks CI would fail on, screenshot UI changes, push, and write the PR like the repo's recent ones. Use for /create-deep-pr, a PR that /deep-plan or /orchestrate-deep-plans asks for, or "open a PR" where no repo-specific PR skill is installed.
argument-hint: [issue link] [--ready] [--skip-tests] [notes for the description]
---

# /create-deep-pr

Take the current changes to an open GitHub PR: a draft, unless the user passes `--ready` or says it's ready for review. Push only a HEAD that passed the checks in step 4.

Before any push, also outside `/create-deep-pr`, run `~/.claude/skills/create-deep-pr/scripts/push-preview.sh [<repo>] [<remote>] [<branch>]` and show its output.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

## 1. Understand the change

- The base is `origin/HEAD` (`git symbolic-ref --short refs/remotes/origin/HEAD`). Read `git status`, the uncommitted diff and `git diff origin/HEAD...HEAD`.
- Nothing to commit and nothing ahead of the base: say so and stop.
- A PR already open for this branch (`gh pr view --json url,state`): update that one through the same steps, editing its description in step 6 instead of creating a new PR.
- Work out what changed, why, and how it's tested from the diff and this conversation. Ask only for what you can't infer. The issue or ticket link is usually the one gap: take it from the arguments or the conversation, otherwise leave its section out and say so in the report.

## 2. Branch

- On a branch made for this work: stay there.
- On the base branch or detached: `git switch -c <prefix>/<slug>`, and the uncommitted changes come along.
  - The prefix follows the repo's recent PR branches (`gh pr list --state merged --limit 10 --json headRefName`). With no clear convention, use your GitHub login (`gh api user -q .login`).
  - The slug names the behaviour change in kebab-case ASCII, at most ~40 characters.
- On a branch whose commits are by someone else: ask before committing to it.

## 3. Commit

- Stage files by name. Leave out anything that isn't the task, and list it in the report: scratch notes, `.env*`, credentials, local config. Ask when you're unsure whether an untracked file belongs.
- Match the style of `git log origin/HEAD --no-merges -10`:
  - Subject: Conventional Commits when the log uses them, otherwise a plain-English imperative sentence naming the behaviour change.
  - Body: a short prose paragraph on what was wrong or missing and what happens now, wrapped at ~72 and ending with the session's `Co-Authored-By:` line.
- Make one commit per coherent step. Tests get their own commit only when they're a separate idea. If the repo squash-merges, fewer commits are fine.
- When a git hook fails, fix its cause. `--no-verify` is off the table.

## 4. Check

Build the **CI recipe**: the commands the CI jobs that gate a PR run (`.github/workflows/*` triggered on `pull_request`, or the repo's other CI config), translated into local commands.

- Scope each command to what the branch touched wherever the tooling allows: affected packages, changed modules, the tests of the classes the branch changed.
- With no CI config, use the project's own scripts (`package.json`, `Makefile`, `justfile`, `pyproject.toml`, `pom.xml`) for lint, types, build and tests.
- Leave out jobs that need secrets or deploy infrastructure, and name them in the PR's Tests section.

Run the recipe against the committed HEAD with a clean tree. Run long checks in the background and tell the user. The step is done when every job in the recipe passed.

- On a failure, fix the cause. Commit the fix, amending when it belongs to the same step, and re-run until green.
- If a failure isn't caused by the branch (the base branch is broken, say), stop and tell the user. Push past it only with their say-so, and note it under "Not in this PR".
- Pass `--skip-tests` only when the user asks for it, and say so in the PR's Tests section.
- Once green, confirm the branch still merges cleanly with `git merge-tree --write-tree origin/HEAD HEAD`. On conflicts, tell the user. Rebasing is their call.

## 5. Screenshots

Run this step when the branch changes what a user sees (templates, styles, components, pages or UI copy; tests and stories don't count) and the user hasn't opted out. Follow [`phase-screenshots.md`](phase-screenshots.md): get the app running, capture each changed screen with Playwright, and post the images. The step is done when every changed screen has a screenshot that shows the change, or the report says why one couldn't be taken. Screenshot trouble never holds up the PR.

## 6. Push and open the PR

Run `push-preview.sh <repo-root> origin <branch> [--paths <this task's directories>]` and show its output: the target, each commit, the file count and any suspicious file. Done when it exited 0 with no `SUSPICIOUS` line and no `FLAG` on a commit; otherwise stop and put the lines to the user (exit 2 means the remote has commits the branch lacks, so rebasing or merging is their call).

```bash
git push -u origin <branch>
gh pr create --draft --base <base-branch> --head <branch> --title "<title>" --body-file <file>
```

Drop `--draft` when the user passed `--ready` or said the PR is ready. For an existing PR, run `gh pr edit <number> --body-file <file>` after the push.

The Start here links need the PR's number, so a new PR gets its body in two passes: create it with the rest, then add the links and run `gh pr edit <number> --body-file <file>`.

**Title**: the same kind of sentence as the commit subject.

**Body**: write it to a file in the scratchpad. It's an **inverted pyramid**: a reviewer who stops after any section has read the most important part. Shape it like the repo's recent merged PRs: run `~/.claude/skills/create-deep-pr/scripts/pr-style.sh <repo-root>`, which prints their sections, checklist and link habits and one example body, and don't fetch PRs by hand. Size it to the diff: a one-line fix gets a few lines, and a cross-cutting change gets the full set. Write in plain, specific prose. If the repo has no merged PRs to copy, use these sections, in this order, and only the ones that earn their place:

- `## What`: the behaviour change in user terms, in 1-3 sentences, ending on `**Risk: low | medium | high**: <one-line reason>`. Put `## Why` first when the reason isn't obvious from the what.
- `## Issue`: the issue or ticket link on its own line.
- `## Start here`: 3-7 links to the lines that carry the change (the behaviour change itself, and each seam: an endpoint, a schema change, a flag, a function or component other code uses), ranked by how much a mistake there would hurt, each `[<file>:<line>](<link>): <what it does>`. Make the links with `~/.claude/skills/create-deep-pr/scripts/deep-links.sh <owner/repo> <number> <path:line>...`. Skip it for a diff a reviewer reads in one screen.
- `## Screenshots`: the image lines from step 5, each under a caption saying what it shows and how to reach it (URL, user, flag or data).
- `## Check by hand`: a `- [ ]` list of what only a person can settle, each naming its screen, role, endpoint or table: changed screens and the pages sharing their components, access for a role that should and one that shouldn't, both states of a flag, schema changes against production data and the rolling deploy, API changes against older clients.
- `## Review notes`: what a reviewer might trip over, what was deliberately left undone and the alternative you considered, known gaps and follow-ups.
- `## Changes`: the rest of the files, grouped by role (wiring, tests, mechanical), one line per group. Name classes and functions in backticks and describe the effect.
- `## Tests`: the tests added or changed and what each one pins, whether they were falsified (change reverted, tests fail), the step 4 checks that actually ran and passed, and any manual verification the user did.
- `## Not in this PR`: related things you noticed and left out.

End the body with the session's PR attribution line.

## 7. Copilot review

```bash
gh pr edit <number> --add-reviewer @copilot
```

It's a nice-to-have. If it fails, for example because Copilot review isn't enabled for the repo, note it in the report and move on.

## 8. Report

End with the PR link on its own line so it's clickable. Follow it with 2-3 lines covering:

- the branch, and whether the PR is a draft or ready
- the checks that ran
- whether screenshots were posted, or why not
- whether Copilot was requested
- files left out of the commit
