# Subagent protocol

Every spawn from `/deep-plan` or `/orchestrate-deep-plans` follows this. The orchestrator's context is the long-lived one: each token in it is re-read on every later turn, so a read early in a run is paid for again on each turn after it. These rules keep that context small.

A spawn is ready when its brief names a model and ends with a reply cap.

## Delegate or read

- **Read it yourself** when the content is small or the session is near its end: Grep first, then Read with `offset`/`limit` for the lines you will edit or verify. Files over 300 lines get targeted reads only.
- **Delegate** bulk reading while a phase or more of the run lies ahead: the subagent reads, and only its capped reply lands here. A fresh agent starts with its own system prompt (~25k tokens) and reads the content again, so a one-off read costs more delegated than read; delegation pays by keeping a long-lived context small.
- Architecture, judgment calls and edits to code you must reason about stay in the orchestrator; a subagent's draft is input to them.
- **Batch the orchestrator's commands:** every turn re-reads the whole context, so run related shell commands in one call and poll only on a watcher event.
- **Fresh context for late phases:** a long phase late in a run (gate, verify, fix and land after a build) runs in a fresh subagent that resumes from the ledger.

## Model

Every spawn names its model; an unnamed one inherits the session's, usually Opus.

| Model | Work |
| --- | --- |
| `haiku`, the *cheap subagent* | recon search, inventory, security pass, screenshot comparison, mechanical checks |
| `sonnet`, the default | builders, background drafts, domain stories |
| `opus`, the *strong subagent* | code-review gates, `/diagnosing-bugs`, planning and landing hand-offs, correctness-critical stories (money, dates, concurrency, auth, migrations) |

A `haiku` bulk read can spend more on thinking than on its reply: ask it for a direct answer with no extended reasoning.

## Brief

- Static rules first, then the task, then the variable part (paths, a diff index) last, so briefs share a prompt-cache prefix.
- Name files by path; the subagent reads them itself.
- A subagent that reviews a diff gets the **review pack**: `~/.claude/skills/deep-plan/scripts/review-pack.sh . <base> WORKTREE <scratch>/pack` writes one filtered diff per changed file and prints an index (`+a -d <path> → <diff file>`, what it skipped, totals). Put that index last; it reads the diffs of its axis in place of running `git diff`.

## Reply cap

Every brief ends with its cap:

- Default: at most 8 lines, `NO_PREAMBLE`; findings as a table or bullets, each starting `file:line`.
- Work that ends in a commit or files: one line, `COMMITTED <sha>`, `FAILED <why>` or the paths written. The detail lives in those files.

A reply is leads: check each number and line you act on with a targeted read.
