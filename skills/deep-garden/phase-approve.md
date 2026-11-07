# Approve or reject

Act on the user's decision for each numbered entry of the newest report (`--report <date>` names an older one). Start with `garden.py entry <n…> [--report <date>]`: one `ENTRY <n> <slug> <branch> <default> <worktree> team|solo in <path>` line each, `DECIDED <decision>` before `in` when it was already settled; say so for those and leave them. The report's `.md` (`garden.py report`) holds each entry's change and test command.

## Approve

Approving pushes nothing by itself. Per entry, in order:

1. Rebase onto the default branch: `git -C <worktree> fetch -q origin <default> && git -C <worktree> rebase origin/<default>`. A conflict → `git -C <worktree> rebase --abort`, tell the user, then `garden.py decide <n> failed "rebase conflict"` and clean up (below); the next pass may propose it afresh. When the rebase moved the base, rerun the entry's test command; a new failure → tell the user and stop this entry.
2. `solo` → preview `~/.claude/skills/create-deep-pr/scripts/push-preview.sh <path> origin <branch>:<default> --paths <the dirs the commits touch>`, shown verbatim, and ask for a yes to this one push, naming repo, branch and target. The yes counts only when the preview ends `FLAGS 0` or the user has answered each `FLAG` and `SUSPICIOUS` line; the approve command itself is no yes. On the yes: `git -C <path> push origin <branch>:<default>`, one Bash call per repo, never chained; then `garden.py decide <n> pushed <sha>` with `<sha>` = `git -C <worktree> rev-parse HEAD`. A push the remote rejects → offer `/create-deep-pr` as for `team`.
3. `team` → preview `push-preview.sh <path> origin <branch> --paths <…>`, shown verbatim, and offer `/create-deep-pr` from the worktree (invoking it is the user's yes for its push). Once it prints the PR: `garden.py decide <n> pr <url>`.

Done per entry when it is `DECIDED pushed` or `DECIDED pr`, or the user has its failure.

## Reject

Per entry: `garden.py reject <n> "<the user's why, else: rejected in the <date> garden pass>"`. It appends the slug to the repo's rejected file and decides the entry `rejected`. When the why is a lasting architectural decision a future reader would need ("the two parsers differ on purpose"), offer to record it as an ADR with the `adr` or `domain-modeling` skill as well. Then clean up.

Done per entry when it is `DECIDED rejected`.

## Clean up

After a decision other than `pr` (the PR still needs its branch): `git -C <path> worktree remove --force <worktree>` and `git -C <path> branch -D <branch>`. Done when `git -C <path> worktree list` no longer shows it.
