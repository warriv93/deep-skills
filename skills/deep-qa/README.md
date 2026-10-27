# /deep-qa

QAs a change and writes one findings file with a verdict: `pass`, `fixable` or `blocked`. It fixes nothing; the caller does (deep-plan's fix loop, or orchestrate-deep-plans' fix stories).

## What it checks

Review lenses (`review` mode): defects and spec through `code-review`, design (strategic programming: shallow modules, leaking information, bolted-on special cases) and security. Verify lenses (`verify` mode): the contract, P1 journeys in the real app, accessibility (axe-core, keyboard, reflow) and performance (indexes, N+1, blocking migrations, Lighthouse). `full` runs both. Each lens's trigger and bar are in `LENSES.md`.

## Use

```
/deep-qa [review | verify | full] [base ref]
```

deep-plan calls it at its Phase 3 gate (`review`), Phase 4 (`verify`) and the second review gate. `scripts/a11y.mjs` is a copy of the author's `feature-qa` script; keep them identical.
