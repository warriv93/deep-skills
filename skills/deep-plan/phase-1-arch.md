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

### Longevity gates

Three more gates keep the code from rotting between reviews, each failing with output that names its fix. Decide once, here, which the repo gets: one too small for a gate to pay off (a script, a prototype) gets none. A gate the repo already runs is pinned as it is; a new tool is added only when the repo's package manager or build installs it. `architecture.md` gets a **Longevity gates** section: each gate's one-line why, or why it was skipped.

- **dup**, any stack jscpd reads (JS/TS, Java, Kotlin, Swift…): `dup: ~/.claude/skills/deep-plan/scripts/new-clones.sh . <base branch>`. It fails only on clones the base branch lacks, so existing duplication never blocks it, and prints each new clone with its fix.
- **boundaries**, when `architecture.md` names modules or layers: one rule per forbidden dependency in the stack's tool (dependency-cruiser or eslint `import/no-restricted-paths` for JS/TS, ArchUnit or Konsist tests inside the test gate for JVM), each message naming the rule and the fix: `domain must not import infra: depend on the port in domain/ports`.
- **size**: limits as errors in the linter the repo already runs (eslint `max-lines-per-function` and `complexity`, detekt `LongMethod` and `CyclomaticComplexMethod`, SwiftLint `function_body_length` and `cyclomatic_complexity`). Today's violations go into the linter's baseline (`eslint --suppress-all`, detekt's baseline, `swiftlint --write-baseline`), so only new code must meet the limit. An inline suppression carries its reason, enforced in eslint by `@eslint-community/eslint-comments/require-description`.

Done when `gates.sh .` exits 0.

Install `/setup-pre-commit` and `git-guardrails-claude-code` if the repo lacks them.

Checkpoint.
