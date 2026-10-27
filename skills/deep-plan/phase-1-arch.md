# Phase 1 — Deep Modular Architecture & Verification Contract

## Architecture

`architecture.draft.md` exists → reconcile it against the signed-off `spec-brief.md` first and build on what survives; delete it once `architecture.md` is written.

Run `/codebase-design` to shape the feature into deep modules:

- Single responsibility per module, narrow interface (1–3 methods).
- Dependencies injected through constructors, so core logic is pure and testable without heavy mocks.
- Seams that let each slice be built and tested in isolation.
- Platform constraints confirmed in Phase 0 honored (edge, serverless, document store…).
- Built on `CONTEXT.md`, ADRs and the recon note's reuse list; view/state seams derived from the signed-off mock (UI work).

Write the result to `.deep-plan/architecture.md`: modules, interfaces, seams, and which existing code each reuses. Phase 2 plans from this file.

## Pin the verification contract

The **contract** is the gate set, pinned as `.deep-plan/contract.cmds`: one `<name>: <command>` line per gate, run from the repo root by `scripts/gates.sh` (SKILL.md, Contract runs). `gates.sh .` alone lists the gates it detects (test, lint, typecheck, format, coverage); write those into the file, and add a line for each CI job that gates a PR and that no detected gate covers (build, e2e). The install command and the single-test-file command are templates, so they go on the ledger instead.

Done when `gates.sh .` exits 0.

Install `/setup-pre-commit` and `git-guardrails-claude-code` if the repo lacks them.

Checkpoint.
