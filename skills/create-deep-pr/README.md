# /create-deep-pr

Takes finished work in any GitHub repo to a draft pull request: branched, committed, checked the way CI would check it, with screenshots of changed screens and a body written like the repo's recent PRs. Use it to open a PR by hand, or when `/deep-plan` or `/orchestrate-deep-plans` asks for one.

## What it does

- Reads the repo's conventions instead of assuming them: the branch prefix from recent merged PR branches (your GitHub login when there's no clear pattern), the commit style from `git log`, and the base from `origin/HEAD`.
- Branches off when you're on the base branch, stages files by name and leaves scratch notes, `.env*` and local config out of the commit (listed in the report). It asks before committing to a branch whose commits are someone else's.
- Builds a CI recipe from the workflows that gate a PR (or the project's own scripts when there's no CI config), scoped to what the branch touched, and fixes failures until every job passes. A failure the branch didn't cause stops it and asks you.
- For UI changes, boots the app (an instance already running counts only if it serves this checkout and started after HEAD), screenshots each changed screen with Playwright, with before and after shots when the app starts fast, and posts them to a `pr-screenshots` orphan branch.
- Writes the body as an inverted pyramid shaped like 3-5 of the repo's recent merged PRs, with deep links into the diff for the lines that carry the change. Updates the PR instead when one is already open for the branch.
- Requests a Copilot review and ends with the PR link, the checks that ran and the files left out.

What leaves the machine: the branch, the `pr-screenshots` branch, the PR and the Copilot request. The skill pushes on its own once the checks are green, so invoking it is the go-ahead. Rebasing on a conflict, and pushing past a failure the branch didn't cause, wait for you.

## Use

```
/create-deep-pr [issue link] [--ready] [--skip-tests] [notes for the description]
```

- `--ready` opens the PR ready for review instead of as a draft.
- `--skip-tests` skips the checks, only when you ask for it, and the PR's Tests section says so.
- Without an issue link the Issue section is left out and the report says so.

## Install

```sh
./install.sh
```

Run it from the repo root; it symlinks every skill into `~/.claude/skills/`. Keep the folder name `create-deep-pr`, since `SKILL.md` calls `~/.claude/skills/create-deep-pr/scripts/deep-links.sh`.

Also needs:

- `git` and `gh`, logged in with push access to the repo.
- The Playwright MCP tools for screenshots, or the repo's own Playwright/e2e setup, which the skill uses when it has one.
- `/run` or a project skill that launches the app, when present; otherwise the run recipe comes from the README, `docs/`, launch configs and `package.json` scripts.

## Scripts

- `scripts/post-screenshots.sh <repo-dir> <png>...` commits the PNGs to `pr-screenshots` under the branch's name through a throwaway index, so the working tree, index and HEAD stay untouched, and prints one markdown image line per file, pinned to that commit.
- `scripts/push-preview.sh [<repo>] [<remote>] [<branch>] [--paths <dirs>]` prints what a push would send: the target (new or existing), each commit with flags for an old author date, another author or files outside `--paths`, the file totals and suspicious files (`.env*`, keys, `node_modules`, `.DS_Store`, large files, secret-like lines). It exits 2 when the remote has commits the branch lacks.
- `scripts/deep-links.sh <owner/repo> <pr-number> <path[:line[:L]]>...` prints a link into the PR's diff for each path and line.

`tests/run.sh` checks `push-preview.sh` against a throwaway repo with a local bare remote.

Outside Claude Code (Antigravity, Gemini) the skill loads `claude-tool-map` first, which `install.sh` links when `~/.gemini/config/` exists.
