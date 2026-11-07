---
name: deep-garden
description: The monthly gardening pass over the product codebases your agents build: finds churn hotspots and duplication, surveys them for deepening refactors, drafts the best few as structural branches, and writes a report whose refactors you approve or reject. Use for "/deep-garden", "garden the codebases", "approve garden refactors".
disable-model-invocation: true
argument-hint: [approve <n…> | reject <n…> [why]] [--report <YYYY-MM-DD>]
---

# /deep-garden

Code that agents build decays where it changes most: copies pile up, special cases bolt on, modules go shallow. This skill finds **hotspots** (files with high churn over the last 90 days crossed with size), has each repo's hotspots surveyed for **candidates** (deepening refactors, in the `codebase-design` vocabulary), drafts the best few as **structural** branches (behaviour unchanged, tests green), and leaves a report you answer entry by entry. It never pushes on its own. `/deep-improve` is its weekly sibling over skill findings; this one gardens product code.

Outside Claude Code (Antigravity, Gemini): activate the `claude-tool-map` skill first and translate every tool, model and command through it.

**Branch on the arguments:**

- none → [the pass](phase-pass.md). A monthly schedule runs it with nobody watching: the run asks nothing, and every question goes into the report's Questions section.
- `approve <n…>` or `reject <n…> [why]` → [approve or reject](phase-approve.md).

## The helper

`~/.claude/skills/deep-garden/scripts/garden.py` (written `garden.py` below) does every deterministic step and prints one line per fact, a path always last; its docstring lists the subcommands. It keeps each report's state in `~/.podium/garden/<YYYY-MM-DD>.json` (entries, repo, branch, default branch, worktree, team or solo, decision) and borrows `/deep-improve`'s `improve.py` for git and report state. Edit that file only through the helper.

Config: `~/.podium/garden.json` `{"repos": [...], "cap": 3}`. `repos` are checkouts to garden; without them, `garden.py repos` gardens every repo with a `.deep-plan/` under `~/gitrepos` (a `/deep-plan` or `/orchestrate-deep-plans` run, found through its worktrees too) that had commits in the last 90 days. `cap` is the most refactors drafted per repo.

## Rejected candidates

A rejection is a line in the repo's `.deep-plan/garden-rejected.md` (`- <slug> (<date>): <why> — <files>`), written by `garden.py reject`; `select` skips that slug and the survey reads the file, so the pass never proposes it again. A line, not an ADR: most rejections are "not this" calls that need no commit, push or team review, and `.deep-plan/` is where the run's history already lives. A why that is a lasting architectural decision also earns an ADR (phase-approve.md), since `improve-codebase-architecture` honours `docs/adr/` on its own.

## The report

`~/.podium/garden/<YYYY-MM-DD>.md`, the human half beside the helper's `.json`:

```markdown
# Garden pass <YYYY-MM-DD>

## <n>. <repo name> · <slug> — <title>
Candidate: <strength> · <files> · hotspot <score> [· design ×<runs>]
Change: <one or two lines: what the refactor deepens, and the deletion test it now passes>
Branch: garden/<slug> · <sha7> · <team: offers /create-deep-pr | solo: pushes to <default>>
Tests: <command> — pass | fail: <first failing line>
Push preview:
    <push-preview.sh output, verbatim>

## Questions
- <repo> — <what the run would have asked, and what it assumed>

## Skipped
- <repo> <slug or —> — <why>
```
