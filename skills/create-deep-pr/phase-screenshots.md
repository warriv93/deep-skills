# Screenshots of UI changes

Step 5 of `/create-deep-pr`. The goal is that a reviewer sees each changed screen the way a user would, with the change on it.

## 1. Pick the screens

From the diff, list each screen where the change shows up and the state that makes it visible. Changes often sit behind a guard: a feature flag, a role, a config value or a data condition. For each one, note what turns it on. Drop files that change nothing visible, such as a type-only refactor. If nothing is left, record that in the report and skip the rest.

## 2. Get the app running on this branch

An instance that's already running counts only if it serves this checkout and started after HEAD was committed. To check:

1. Find the port's process with `lsof -ti :<port> -sTCP:LISTEN`.
2. Get its working directory with `lsof -a -p <pid> -d cwd` and its start time with `ps -o lstart= -p <pid>`.
3. Compare them with the repo root and `git log -1 --format=%cd`.

If it doesn't count, find the **run recipe**: how this repo boots in dev, where it serves, and how to log in. Look in this order, taking the first that answers:

1. A project skill or `/run` that covers launching the app.
2. The README, `CONTRIBUTING.md` and `docs/`.
3. `.claude/launch.json`, `.run/` and `.vscode/launch.json`.
4. The `dev`/`start` scripts in `package.json`, a `Makefile`, `docker-compose*`.

For login and data, prefer what the repo already has: dev users in its docs or seed data, or an existing Playwright/e2e setup with fake-auth fixtures and API mocks. With such a setup, write a throwaway spec that uses those fixtures and calls `page.screenshot({ path })` with scratchpad paths, run it through the repo's e2e command, and delete it afterwards. That replaces the MCP capture in section 3, but the subagent check there still applies.

Start the app in the background, logging to a file. Poll its URL until it answers, for at most 10 minutes. If the recipe needs secrets, a VPN or a cluster port-forward you can't set up, or the boot fails, skip the screenshots and name the blocker in the report. Once you're done, stop what you started and leave anything that was already running.

## 3. Capture

Use the Playwright MCP tools to log in and set up the state, and `shots.mjs` to take the shots:

1. Set the viewport to 1440x900 with `browser_resize`.
2. Navigate to the page and log in.
3. Set up the state from section 1, then save the session with `browser_run_code_unsafe`: `await page.context().storageState({ path: '<scratchpad>/state.json' })`.
4. Take every screen reachable by URL in one call: `~/.claude/skills/create-deep-pr/scripts/shots.mjs --max 1440 --storage <scratchpad>/state.json --out <scratchpad>/shots '<url>@1440x900#<screen-and-state>' ...`, naming each shot after the screen and state, like `settings-billing-address`. `--max 1440` keeps them full width, since they go on the PR. It prints `SHOT <file> <w>x<h>`, or `SHOT_FAILED <url> <reason>` for one to retake. A screen only reachable by clicking gets `browser_take_screenshot` instead, with an absolute scratchpad `filename`, so the PNGs stay out of the working tree.
5. Never read a PNG yourself. Give a `haiku` or `sonnet` subagent every file path with what the shot must show, and have it open each and reply one line per file: `<file> OK` or `<file> RETAKE <what it shows instead>`. Retake each `RETAKE` and have the subagent check it again. A login page, an error page or an empty state doesn't count.

Frame the changed region together with its surrounding form or table: pick the viewport height to fit it, or take an element screenshot with `browser_take_screenshot`.

For each shot, note how to reach the screen: the URL, the user, and the flag or data that makes the change visible. It goes in the caption, so a reviewer can find the screen and regression-test it.

When the app runs on mocks or starts in under a minute, also capture each screen **before** the change: run it from a worktree at the merge base (`git worktree add --detach <scratch>/base $(git merge-base origin/HEAD HEAD)`, its dependencies installed), name the files `<screen>-before.png` and `<screen>-after.png`, and remove the worktree afterwards. Slower apps get after shots only.

## 4. Post

```bash
<this skill's folder>/scripts/post-screenshots.sh <repo-root> <png>...
```

The script commits the PNGs to the repo's `pr-screenshots` orphan branch, in a folder named after the PR branch, and pushes it. It prints one markdown image line per file, pinned to that commit, and leaves the working tree, index and current branch alone. Put the lines in the PR's Screenshots section, each under its caption; a before and after pair goes side by side in a two-column table.
