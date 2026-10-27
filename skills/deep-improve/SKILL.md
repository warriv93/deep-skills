---
name: deep-improve
description: The weekly improvement pass over orchestrate findings: drafts a fix for each recurring finding on its own branch, re-measures last week's token fixes, and writes a report whose fixes you approve or reject. Use for "/deep-improve", "work the findings", "approve improvement fixes".
disable-model-invocation: true
argument-hint: [approve <n…> | reject <n…> [why]] [--report <YYYY-MM-DD>]
---

# /deep-improve

Orchestrator runs record **findings**: a problem a skill, the `podium` tool or an agent keeps causing, under a `key` reused each time it recurs. This skill turns the recurring ones into drafted fixes the user approves one by one. It never pushes on its own.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

**Branch on the arguments:**

- none → [the pass](phase-pass.md). A weekly schedule runs it with nobody watching: the run asks nothing, and every question goes into the report.
- `approve <n…>` or `reject <n…>` (also "push 1, 3", "reject 2") → [approve or reject](phase-approve.md).

## The helper

`~/.claude/skills/deep-improve/scripts/improve.py` (written `improve.py` below) does every deterministic step and prints one line per fact; its docstring lists the subcommands. It keeps each report's state in `~/.podium/improve/<YYYY-MM-DD>.json`: the numbered entries, their repo, branch, default branch, worktree, token baseline and decision. Edit that file only through the helper.

Config: `~/.podium/improve.json` `{"findings": "<remote>", "remotes": [...], "cap": 5}`. `findings` is the git remote this machine's runs record findings to; `remotes` are every remote the pass reads, defaulting to `findings`; `cap` is the most fixes drafted per pass. No remote configured → `improve.py remotes` prints nothing: stop and tell the user to set one.

## The report

`~/.podium/improve/<YYYY-MM-DD>.md`, the human half beside the helper's `.json`:

```markdown
# Improvement pass <YYYY-MM-DD>

## <n>. <key> — <title>
Finding: <kind> · <target> · ×<runs> runs · <severity>[ · ~<saving>/wk] · fix: <fix type>
Moment: <the latest moment>
Change: <one or two lines: what the commit changes and why that stops the recurrence>
Repo: <repo> · branch improve/<key> · <sha7>
Tests: <command> — pass | fail: <first failing line>
Push preview:
    <push-preview.sh output, verbatim>

## Re-measured
<KEPT/REVERT lines>

## Skipped
- <key> — <why>
```

A revert entry is numbered like a fix, with `Change: revert <sha7>, no drop in tokens/week (~<before> → ~<after>)`.
