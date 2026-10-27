# Approve or reject

Act on the user's decision for each numbered entry of the newest report (`--report <date>` names an older one). Start with `improve.py entry <n…> [--report <date>]`: one `ENTRY <n> <key> <kind> <repo> <branch> <default> <worktree>` line each, `DECIDED <decision>` appended when it was already settled; say so for those and leave them. The report's `.md` (`improve.py report`) holds each entry's change and test command.

## Approve

Per entry, in order:

1. Rebase onto the default branch: `git -C <worktree> fetch -q origin <default> && git -C <worktree> rebase origin/<default>`. A conflict → `git -C <worktree> rebase --abort`, tell the user, then `improve.py decide <n> failed "rebase conflict"` and clean up (below); the next pass drafts it afresh. When the rebase moved the base, rerun the entry's test command; a new failure → tell the user and stop this entry.
2. Preview: `~/.claude/skills/create-deep-pr/scripts/push-preview.sh <repo> origin <branch>:<default> --paths <the dirs the commit touches>`, shown verbatim. `BLOCKED` → back to 1.
3. Ask for a yes to this one push, naming repo, branch and target. The yes counts only when the preview ends `FLAGS 0` or the user has answered each `FLAG` and `SUSPICIOUS` line. The approve command itself is no yes.
4. On the yes: `git -C <repo> push origin <branch>:<default>`, one Bash call per repo, never chained. A push the remote rejects (a protected default branch) → tell the user and offer `/create-deep-pr` from the branch instead.
5. Record it: `improve.py decide <n> pushed <sha>` with `<sha>` = `git -C <worktree> rev-parse HEAD`, then, for a fix (not a revert), `podium finding resolve <key> --sha <sha> --repo <basename of repo> $(improve.py remotes)`.

Done per entry when it is `DECIDED pushed` and its finding resolved, or the user has its failure.

## Reject

Per entry: for a fix, `podium finding wontfix <key> --why "<the user's why, else: rejected in the <date> improvement pass>" $(improve.py remotes)`; a rejected revert leaves its finding as it is. Then `improve.py decide <n> rejected "<why>"` and clean up.

Done per entry when it is `DECIDED rejected`.

## Clean up

After any decision: `git -C <repo> worktree remove --force <worktree>` and `git -C <repo> branch -D <branch>`. Done when `git -C <repo> worktree list` no longer shows it.
