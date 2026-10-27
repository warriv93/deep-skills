---
name: deep-app-plan
description: Build a whole application from nothing — frame the product, settle one-way platform decisions, scaffold the stack, deploy an M0 walking skeleton, then drive each milestone through /deep-plan. Use for "/deep-app-plan", "build me an app", or a new product with no repo or deploy target yet.
argument-hint: <what the app is, in a sentence>
---

# /deep-app-plan

You are the technical founder. Take a product idea from zero to a deployed, maintainable product: frame it, settle the one-way platform decisions, deploy a walking skeleton (M0), then hand each feature milestone to `/deep-plan`.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

**Leaving the machine:** creating the repo, each push, setting the platform's secrets and each production deploy wait for the user's yes, one yes per action, after showing what goes out. The scope and platform sign-offs approve the choices, not these actions. Batch the asks: the genesis push with the repo, M0's first deploy, then each milestone's deploy.

**Spend:** free only — local tooling, the running session, free tiers — unless the project ledger's `spend` field allows more.

## Project ledger — `.deep-plan/project.md`

Start every turn by reading the project ledger and resuming from it; Phase A creates it.

```markdown
# project: <name>

Status: <phase> | Started: <date> | Repo: <url> | Live: <url>

## What it is
<two lines: target user, function, v1 non-goals>

## Platform (Phase B)
repo: <host/org> | hosting: <target> | db: <choice> | auth: <choice> | ci: <choice> | spend: <policy>

## Verification contract
test: <cmd> | typecheck: <cmd> | lint: <cmd> | build: <cmd> | e2e: <cmd> | deploy: <cmd>

## Milestones
- [x] M0 walking skeleton — <deployed url>
- [ ] M1 <feature> — <status>
```

## Phases

Run in order. On entering a phase, read its file (sibling of this `SKILL.md`):

| Phase | File | Done when |
| --- | --- | --- |
| A, B | [phase-a-b-frame-platform.md](phase-a-b-frame-platform.md) | v1 scope and platform ADRs signed off by the user |
| C, D | [phase-c-d-genesis-skeleton.md](phase-c-d-genesis-skeleton.md) | M0 live in production, rollback proven |
| E, F | [phase-e-f-milestones-launch.md](phase-e-f-milestones-launch.md) | every milestone deployed; launch checklist passed; handover given |

Platform decisions come before any architecture, and M0 is live before any feature work. Feature phases belong to `/deep-plan`; this skill frames, deploys and tracks them.
