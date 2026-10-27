---
name: deep-qa
description: Quality-assure a change — defects, spec, design, security, contract, real-app journeys, accessibility and performance — and return a findings file with a verdict, fixing nothing. Use for "/deep-qa", "QA this", deep-plan's quality gate and verify, or any branch before its PR.
argument-hint: [review | verify | full] [base ref]
---

# /deep-qa

QA one change and report; the caller fixes. The run picks its **lenses** by what the diff touches, runs each, and writes one **findings file** whose verdict tells the caller what to do next. It never edits, commits or pushes: a finding is a row with a concrete fix, for the caller to apply (deep-plan's fix loop, or orchestrate-deep-plans' fix stories).

The lenses, their triggers and their bars live in [LENSES.md](LENSES.md). Tags: `Blocker` (breaks behaviour, a contract or a promise), `Should fix` (fix before merge), `Nit` (worth fixing, never blocks).

## 1. Pin the target

- **Mode:** `review` runs the static lenses (Defects, Spec, Design, Security), `verify` the running ones (Contract, Journeys, Accessibility, Performance), `full` both. Default `full`.
- **Base:** the ref in the arguments, else `origin/HEAD` after `git fetch origin`. `<base>` is the merge-base sha, `git merge-base <ref> HEAD`.
- **Plan files** (`.deep-plan/`, when it exists): the feature's `spec.md` and its acceptance criteria, `spec-brief.md`'s P1 journeys and success criteria, `architecture.md`'s seams, `mock/`, and `contract.cmds`. Without them, the claim is the commit messages and the PR or issue the branch names.
- **Out:** `.deep-plan/findings-<label>.md` when the caller gives a label (`phase-3`, `phase-4`), else `<scratch>/findings.md` in a `mktemp -d` scratch folder.

Done when the base sha is shown, the diff is non-empty, and you know which plan files exist.

## 2. Choose the lenses

Apply LENSES.md's triggers to the diff (`git diff --stat <base>`) and the mode. Write the plan as the findings file's first table: lens, run or skip, and why. Done when every lens of the mode has a row.

## 3. Run them

Build the review pack once: `~/.claude/skills/deep-plan/scripts/review-pack.sh . <base> WORKTREE <scratch>/pack`. Start the static lenses first, in parallel: Defects, Spec, Design and Security are independent subagents under the subagent protocol (`~/.claude/skills/deep-plan/subagent-protocol.md`), each given the pack's index. Then run Contract, and Journeys, Accessibility and Performance against the running app.

Each lens ends on LENSES.md's done-when for it, or as `not run: <reason>` in the findings file. A lens that can't run is never silently dropped.

## 4. Verify and grade

Pool every row. Merge rows naming the same defect. Open each at file:line (or replay its journey step) and keep only rows whose failure you traced yourself. Pre-existing problems the change didn't touch go under **Pre-existing**, untagged, outside the verdict.

The **verdict**:

- `pass`: no Blocker or Should fix.
- `fixable`: every Blocker and Should fix row names its fix, and none needs a decision from the user.
- `blocked`: a row needs the user's decision (the spec contradicts itself, a journey fails with no diagnosed cause, a security Critical with no clear fix), or a lens the change requires couldn't run.

Done when every kept row has a fix and a few words on what you read to confirm it.

## 5. Report

Write the findings file:

```
# QA <label or branch>: <pass | fixable | blocked>, <b> blockers, <s> should fix, <n> nits
<mode>; <base short sha>..<head short sha>

## Lenses
| lens | ran / skipped / not run | why |

## Blockers | ## Should fix | ## Nits
| file:line or journey step | lens | failure | fix |

## Journeys
<each P1 journey: passed, or failed at <step>>

## Pre-existing
<one line each>
```

Then print its first line and its path in chat. Done when the file exists and every lens row in it says ran, skipped or not run.
