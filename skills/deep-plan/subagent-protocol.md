# Subagent protocol

Every spawn from `/deep-plan` or `/orchestrate-deep-plans` follows this. The orchestrator's context is the long-lived one: each token in it is re-read on every later turn, so a read early in a run is paid for again on each turn after it. These rules keep that context small.

A spawn is ready when its brief names a model and effort and ends with a reply cap.

## Delegate or read

- **Read it yourself** when the content is small or the session is near its end: Grep first, then Read with `offset`/`limit` for the lines you will edit or verify. Files over 300 lines get targeted reads only.
- **Delegate** bulk reading while a phase or more of the run lies ahead: the subagent reads, and only its capped reply lands here. A fresh agent starts with its own system prompt (~25k tokens) and reads the content again, so a one-off read costs more delegated than read; delegation pays by keeping a long-lived context small.
- Architecture, judgment calls and edits to code you must reason about stay in the orchestrator; a subagent's draft is input to them.
- **Batch the orchestrator's commands:** every turn re-reads the whole context, so run related shell commands in one call and poll only on a watcher event.
- **Fresh context for late phases:** a long phase late in a run (gate, verify, fix and land after a build) runs in a fresh subagent that resumes from the ledger.

## Model

Every spawn names its model and effort from its job's row in [agent-models.md](agent-models.md), which also defines the *cheap* and *strong subagent* and when to escalate; an unnamed one inherits the session's, usually Opus.

## Brief

- Static rules first, then the task, then the variable part (paths, a diff index) last, so briefs share a prompt-cache prefix.
- Name files by path; the subagent reads them itself, as targeted reads, which the brief states: Grep first, then Read with `offset`/`limit`, and a persisted tool-results file or any file over 300 lines grepped, never read whole.
- A subagent that reviews a diff gets the **review pack**: `~/.claude/skills/deep-plan/scripts/review-pack.sh . <base> WORKTREE <scratch>/pack` writes one filtered diff per changed file and prints an index (`+a -d <path> → <diff file>`, what it skipped, totals). Put that index last; it reads the diffs of its axis in place of running `git diff`.

## Reply cap

Every brief ends with its cap:

- Default: at most 8 lines, `NO_PREAMBLE`; findings as a table or bullets, each starting `file:line`.
- Work that ends in a commit or files: one line, `COMMITTED <sha>`, `FAILED <why>` or the paths written. The detail lives in those files.

A reply is leads: check each number and line you act on with a targeted read.
