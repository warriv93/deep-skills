# Phase E & F — Milestones & Launch Readiness

## Phase E — Milestones via `/deep-plan`

For each open milestone, in order:

1. **Hand off:** mark the milestone `in progress` in the ledger, then ask the user to `/clear` and run `/deep-plan M<n>: <milestone frame>`. `/deep-plan` reads the project ledger's Platform and contract blocks during recon. A milestone with three or more independent stories can run through `/orchestrate-deep-plans <frame>` instead, which drives `/deep-plan` itself.
2. **Resume** when the user re-invokes `/deep-app-plan` after the `/deep-plan` debrief.
3. **Deploy** the milestone to prod and confirm it live.
4. **Record:** tick the milestone in the ledger; add lessons learned to `CLAUDE.md`.

## Phase F — Launch readiness

Every item passes before the app counts as real:

1. **Security audit:** `/security-review` over the full codebase (auth, ACL, secrets, SQL).
2. **Data:** migrations run clean from empty; backups restore; free-tier ceiling defined.
3. **Operations:** custom domain and TLS; error tracking receiving events; rollback path ready.
4. **Cold start:** clone into a clean dir, follow only the README, and reach a local run.
5. **Handover debrief:** shipped vs. frame, non-goals, weak points, inputs the user must supply, recurring costs.
