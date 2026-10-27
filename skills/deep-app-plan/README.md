# /deep-app-plan

Builds a whole application from nothing: frames the product, settles the platform decisions that are hard to reverse, scaffolds the repo, deploys a walking skeleton (M0) to production, then drives each feature milestone through `/deep-plan`. Use it for a new product with no repo or deploy target yet; a feature in an existing codebase belongs to `/deep-plan`.

## What it does

- Grills the product frame with `/grilling` (first user, what v1 does and leaves out, one success signal, the alternatives) and cuts it into milestones: M0, then one per deployable capability. Waits for your sign-off on the v1 scope.
- Asks every platform question you haven't answered in one `AskUserQuestion` pass, each with a recommended default: repo host and licence, hosting, database, auth, CI, auto-deploy and rollback, domain and secrets, spend policy, scale and observability. Records the answers as ADRs through `/domain-modeling` and waits for you to confirm the platform.
- Creates the repo on the chosen host, scaffolds the stack with its ecosystem's CLI, pins the verification contract (including deploy), installs pre-commit hooks and git guardrails, adds a GitHub Actions workflow that runs the contract and deploys on green, and seeds `CLAUDE.md` and `CONTEXT.md`.
- Deploys M0 to production (the thinnest path from client to server to database and back), proves it from the live URL, exercises the rollback once and tags `m0`.
- Hands each milestone to `/deep-plan` (or `/orchestrate-deep-plans` for one with three or more independent stories), then deploys it and ticks it off when you come back.
- Ends on a launch-readiness checklist: a full `/security-review`, migrations and backups, domain, TLS and error tracking, a cold start from the README alone, and a handover debrief.
- Spends nothing beyond local tooling and free tiers unless the ledger's `spend` field allows more.

What leaves the machine: a new repo on the chosen host, its pushes, the platform's secrets, the CI pipeline and production deploys. Each of those waits for your yes, one per action; the v1 scope and platform sign-offs approve the choices, not the actions.

## Use

```
/deep-app-plan <what the app is, in a sentence>
```

State lives in `.deep-plan/project.md`, the project ledger, which every turn reads first. For each milestone the skill asks you to `/clear` and run `/deep-plan M<n>: <milestone frame>`, then re-invoke `/deep-app-plan` after the debrief.

## Install

```sh
./install.sh
```

Run it from the repo root; it symlinks every skill into `~/.claude/skills/`.

Skills it calls: `/deep-plan` (with everything it needs, see [its README](../deep-plan/README.md)), `/grilling`, `/domain-modeling`, `/writing-for-agents`, `/setup-pre-commit`, `git-guardrails-claude-code` and `/security-review`. `/orchestrate-deep-plans` is optional, for milestones with many stories.

Also needs an account on the repo host and the hosting target you pick, with their CLIs logged in. The skill names neither CLI; which ones depends on the Phase B answers.

Outside Claude Code (Antigravity, Gemini) the skill loads `claude-tool-map` first, which `install.sh` links when `~/.gemini/config/` exists.
