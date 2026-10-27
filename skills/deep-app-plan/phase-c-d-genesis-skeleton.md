# Phase C & D — Genesis & Walking Skeleton

## Phase C — Genesis (repo, scaffold, tooling)

1. **Create the repo** on the chosen host, with licence and a README holding the Phase A frame.
2. **Scaffold the stack** with the ecosystem's CLI (`create-*`, `cargo new`, `uv init`…).
3. **Pin the contract:** install, test, single-test-file, typecheck, lint, format, build, e2e, deploy — into the ledger. Run each now until it exits 0.
4. Install `/setup-pre-commit` and `git-guardrails-claude-code`.
5. **CI & deploy pipeline:** a GitHub Actions workflow running the contract on push/PR, plus a deploy job on green.
6. **Seed agent docs with `/writing-for-agents`:** `CLAUDE.md` (the unwritten conventions only) and `CONTEXT.md` (glossary, ADRs).

## Phase D — Walking skeleton (M0)

Deploy the thinnest end-to-end slice to **production**:

1. Thinnest real path: client → server → DB → back.
2. Wire the deploy: env vars set on the platform, DB migrations running, push to main triggers a live deploy.
3. **Prove it from outside:** hit the live URL and see a DB round-trip in prod; exercise the rollback path once.
4. Commit and tag `m0`; record the live URL in the ledger.

**Gate:** M0 live in production.
