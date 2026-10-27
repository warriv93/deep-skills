#!/usr/bin/env bash
# Usage: post-screenshots.sh <repo-dir> <png>...
# Commits the PNGs to the repo's pr-screenshots orphan branch under <current-branch>/ and pushes it.
# Prints one markdown image line per file, pinned to that commit, so a later upload can't change
# what an existing PR shows. Uses a throwaway index: the working tree, index and HEAD stay untouched.
set -euo pipefail

root="$(cd "$1" && git rev-parse --show-toplevel)"; shift
[ $# -gt 0 ] || { echo "usage: post-screenshots.sh <repo-dir> <png>..." >&2; exit 2; }
ref=pr-screenshots
dir="$(git -C "$root" branch --show-current | tr '/' '-')"
[ -n "$dir" ] || { echo "Detached HEAD: switch to the PR branch first." >&2; exit 2; }
# owner/repo from git@github.com:o/r.git or https://github.com/o/r(.git)
slug="$(git -C "$root" remote get-url origin | sed -E 's#\.git$##; s#^.*github\.com[:/]##')"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
export GIT_INDEX_FILE="$tmp/index"

# Retry when someone else pushed screenshots between our fetch and push.
for attempt in 1 2 3; do
  rm -f "$GIT_INDEX_FILE"; parent=""
  if git -C "$root" fetch --quiet origin "refs/heads/$ref" 2>/dev/null; then
    parent="$(git -C "$root" rev-parse FETCH_HEAD)"
    git -C "$root" read-tree "$parent"
  fi
  for f in "$@"; do
    blob="$(git -C "$root" hash-object -w "$f")"
    git -C "$root" update-index --add --cacheinfo "100644,$blob,$dir/$(basename "$f")"
  done
  tree="$(git -C "$root" write-tree)"
  commit="$(git -C "$root" commit-tree "$tree" ${parent:+-p "$parent"} -m "Screenshots for $dir")"
  if git -C "$root" push --quiet origin "$commit:refs/heads/$ref"; then
    for f in "$@"; do
      name="$(basename "$f")"
      echo "![${name%.*}](https://github.com/$slug/blob/$commit/$dir/$name?raw=true)"
    done
    exit 0
  fi
  echo "Push of $ref rejected (attempt $attempt), refetching." >&2
done
exit 1
