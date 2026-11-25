#!/usr/bin/env bash
# Usage: land.sh <repo> <branch> [--base <base>]
# Lands a finished branch on its base (default main) without touching <repo>'s working tree: rebases it onto
# <base> in a temporary detached worktree (which also flattens its merge commits), symlinks <repo>/node_modules
# into it when present, runs the contract there (gates.sh . --logs .deep-plan/contract.logs), then fast-forwards
# <base>: with `merge --ff-only` in the worktree that has it checked out, else as a ref update in <repo>.
# <branch> moves to the landed commits too unless some worktree has it checked out. It never pushes.
# Exit 0 landed or nothing to land, 1 when it stopped, 2 on a bad argument. Output:
#   NOTHING <branch> is already in <base>
#   CONFLICT <file>...          the rebase stopped: aborted, temporary worktree removed
#   GATES-FAILED <gate>... KEPT <worktree>   the gates' output above it; the worktree stays for a look
#   DIRTY <worktree>            <base> is checked out there with uncommitted changes: nothing moved
#   LANDED <base> <short sha>
#   NEXT <the push-preview.sh call to show before any push>
set -uo pipefail

usage="Usage: land.sh <repo> <branch> [--base <base>]"
[ $# -ge 2 ] || { echo "$usage" >&2; exit 2; }
repo="$1"; branch="$2"; shift 2; base=main
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base="${2:-}"; shift 2;;
    *) echo "unknown argument $1" >&2; exit 2;;
  esac
done
repo="$(git -C "$repo" rev-parse --show-toplevel 2>/dev/null)" || { echo "not a git repo: $1" >&2; exit 2; }
for ref in "$branch" "$base"; do
  git -C "$repo" rev-parse --verify -q "refs/heads/$ref" >/dev/null || { echo "no branch $ref in $repo" >&2; exit 2; }
done
here="$(cd "$(dirname "$0")" && pwd)"

# checked_out <branch>: the worktree that has it checked out, if any
checked_out() {
  git -C "$repo" worktree list --porcelain | awk -v want="branch refs/heads/$1" '/^worktree /{w=substr($0,10)} $0==want{print w; exit}'
}

if git -C "$repo" merge-base --is-ancestor "$branch" "$base"; then
  echo "NOTHING $branch is already in $base"; exit 0
fi

holder="$(checked_out "$base")"
dirty() { [ -n "$holder" ] && [ -n "$(git -C "$holder" status --porcelain --untracked-files=no)" ]; }
dirty && { echo "DIRTY $holder: $base is checked out there with uncommitted changes; commit or stash them, then rerun"; exit 1; }

tmp="${TMPDIR:-/tmp}"; scratch="$(mktemp -d "${tmp%/}/land.XXXXXX")"; tree="$scratch/$(basename "$repo")"
drop() { git -C "$repo" worktree remove --force "$tree" >/dev/null 2>&1; rm -rf "$scratch"; }
git -C "$repo" worktree add -q --detach "$tree" "$branch" || { rm -rf "$scratch"; exit 1; }
[ -d "$repo/node_modules" ] && [ ! -e "$tree/node_modules" ] && ln -s "$repo/node_modules" "$tree/node_modules"

if ! git -C "$tree" rebase -q "$base" >/dev/null 2>&1; then
  files="$(git -C "$tree" diff --name-only --diff-filter=U | tr '\n' ' ')"
  git -C "$tree" rebase --abort >/dev/null 2>&1
  drop
  echo "CONFLICT ${files% }"; exit 1
fi

out="$(cd "$tree" && "$here/gates.sh" . --logs .deep-plan/contract.logs 2>&1)"; rc=$?
echo "$out"
if [ $rc != 0 ]; then
  failed="$(awk '/^FAIL /{print $2}' <<<"$out" | paste -sd ' ' -)"
  echo "GATES-FAILED ${failed:-exit $rc} KEPT $tree"; exit 1
fi

sha="$(git -C "$tree" rev-parse HEAD)"
dirty && { drop; echo "DIRTY $holder: $base is checked out there with uncommitted changes; commit or stash them, then rerun"; exit 1; }
if [ -n "$holder" ]; then
  git -C "$holder" merge -q --ff-only "$sha" || { drop; exit 1; }
else
  git -C "$repo" update-ref "refs/heads/$base" "$sha" "$(git -C "$repo" rev-parse "refs/heads/$base")" || { drop; exit 1; }
fi
drop
[ -z "$(checked_out "$branch")" ] && git -C "$repo" branch -f -q "$branch" "$sha"

echo "LANDED $base $(git -C "$repo" rev-parse --short "$sha")"
echo "NEXT ~/.claude/skills/create-deep-pr/scripts/push-preview.sh $repo origin $base --paths <the work's dirs>; push as the user's push rule allows"
