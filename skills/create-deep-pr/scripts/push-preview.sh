#!/usr/bin/env bash
# Usage: push-preview.sh [<repo>] [<remote>] [<branch>|<src>:<dst>] [--paths <dir,dir,...>]
# What `git push <remote> <branch>` (or `<src>:<dst>`) would send, before it goes. Defaults: the current directory,
# origin, the checked-out branch. Writes nothing but git's remote-tracking refs (one fetch).
# --paths names the task's directories; a commit touching files outside them gets a flag.
# Output, one line per fact:
#   TARGET <remote>/<branch> new (base <ref>)          the branch doesn't exist on the remote yet
#   TARGET <remote>/<branch> existing (<n> ahead)
#   COMMIT <sha> <author> <subject> [FLAG ...]         oldest first; flags: older-than-newest <h>h
#                                                      (author date >1h before the newest commit),
#                                                      other-author (not git's user.email),
#                                                      outside-paths <files>
#   FILES <n> +<added> -<deleted>
#   SUSPICIOUS <kind> <path>                           kinds: env, key, node_modules, ds-store,
#                                                      large (>500KB), secret-like (added lines
#                                                      that look like a private key or token)
#   BLOCKED <behind|diverged> (<n> behind, <m> ahead)  exit 2: the remote has commits the branch lacks
#   NOTHING nothing to push                            exit 0
#   FLAGS <n>                                          last line: the FLAG and SUSPICIOUS lines above
# Exit 1 on an unusable argument (no such repo, remote or branch).
set -uo pipefail

paths=""; pos=()
while [ $# -gt 0 ]; do
  case "$1" in
    --paths) paths="${2:-}"; shift 2;;
    *) pos+=("$1"); shift;;
  esac
done
repo="${pos[0]:-.}"; remote="${pos[1]:-origin}"
root="$(cd "$repo" 2>/dev/null && git rev-parse --show-toplevel 2>/dev/null)" || { echo "ERROR $repo is not a git repo" >&2; exit 1; }
g() { git -C "$root" -c core.quotePath=false "$@"; }
branch="${pos[2]:-$(g symbolic-ref --short HEAD 2>/dev/null || true)}"
[ -n "$branch" ] || { echo "ERROR detached HEAD: name the branch" >&2; exit 1; }
src="${branch%%:*}"; [[ "$branch" == *:* ]] && branch="${branch#*:}"   # <src>:<dst> pushes local src to remote dst
[ "$src" = HEAD ] && src="$(g rev-parse HEAD)"
g rev-parse --verify -q "$src^{commit}" >/dev/null || { echo "ERROR no local branch or commit $src" >&2; exit 1; }
g remote get-url "$remote" >/dev/null 2>&1 || { echo "ERROR no remote $remote" >&2; exit 1; }

# Does the branch exist on the remote? ls-remote asks it; a failed ask falls back to the tracking ref.
ls="$(g ls-remote --heads "$remote" "refs/heads/$branch" 2>&1)"; rc=$?
if [ $rc -ne 0 ]; then
  echo "WARN could not reach $remote ($(tail -n 1 <<<"$ls")); using the last fetched state"
  rsha="$(g rev-parse -q --verify "refs/remotes/$remote/$branch" 2>/dev/null || true)"
else
  rsha="$(cut -f1 <<<"$ls" | head -1)"
  [ -n "$rsha" ] && ! g cat-file -e "$rsha^{commit}" 2>/dev/null && g fetch -q "$remote" "$branch" 2>/dev/null
fi
head="$(g rev-parse "$src^{commit}")"

if [ -n "$rsha" ]; then
  range_base="$rsha"
  ahead="$(g rev-list --count "$rsha..$head" 2>/dev/null || echo "?")"
  behind="$(g rev-list --count "$head..$rsha" 2>/dev/null || echo "?")"
  echo "TARGET $remote/$branch existing ($ahead ahead)"
  if [ "$behind" != 0 ]; then
    kind=behind; [ "$ahead" != 0 ] && kind=diverged
    echo "BLOCKED $kind ($behind behind, $ahead ahead): the remote has commits this branch lacks; rebasing or merging is the user's call"
    exit 2
  fi
else
  basebr="$(g symbolic-ref --short "refs/remotes/$remote/HEAD" 2>/dev/null || true)"
  for cand in "$basebr" "$remote/main" "$remote/master" "$remote/develop"; do
    [ -n "$cand" ] && g rev-parse -q --verify "$cand" >/dev/null && { basebr="$cand"; break; }
  done
  [ -n "$basebr" ] || { echo "ERROR $remote has no $branch and no default branch to compare with" >&2; exit 1; }
  range_base="$(g merge-base "$basebr" "$head")"
  echo "TARGET $remote/$branch new (base $basebr)"
fi
[ "$(g rev-list --count "$range_base..$head")" = 0 ] && { echo "NOTHING nothing to push"; exit 0; }

# outside_paths: stdin names, stdout the ones not under any --paths directory.
outside_paths() {
  local f p ok
  while IFS= read -r f; do
    ok=""
    for p in ${paths//,/ }; do
      p="${p%/}"; [ "$f" = "$p" ] || [[ "$f" == "$p"/* ]] && ok=1
    done
    [ -z "$ok" ] && echo "$f"
  done
  return 0
}

flags=0
me="$(g config user.email || true)"
newest="$(g log --format=%at "$range_base..$head" | sort -n | tail -1)"
n=0
while IFS=$'\t' read -r sha at email author subject; do
  n=$((n+1))
  [ $n -gt 30 ] && continue
  fl=""
  hours=$(( (newest - at) / 3600 ))
  [ $((newest - at)) -gt 3600 ] && fl="$fl FLAG older-than-newest ${hours}h"
  [ -n "$me" ] && [ "$email" != "$me" ] && fl="$fl FLAG other-author"
  if [ -n "$paths" ]; then
    outside="$(g diff-tree --no-commit-id --name-only -r -m --root "$sha" | outside_paths | head -3 | paste -sd, -)"
    [ -n "$outside" ] && fl="$fl FLAG outside-paths $outside"
  fi
  [ -n "$fl" ] && flags=$((flags+1))
  echo "COMMIT ${sha:0:7} $author $subject$fl"
done < <(g log --reverse --format='%H%x09%at%x09%ae%x09%an%x09%s' "$range_base..$head")
[ $n -gt 30 ] && echo "COMMIT … $((n-30)) more"

read -r files add del < <(g diff --numstat "$range_base" "$head" | awk '{a+=($1=="-"?0:$1); d+=($2=="-"?0:$2); n++} END {print n+0, a+0, d+0}')
echo "FILES $files +$add -$del"

# Suspicious files: by name, by size, then by what the added lines contain.
sus() { echo "SUSPICIOUS $1 $2"; flags=$((flags+1)); }
while IFS= read -r -d '' meta && IFS= read -r -d '' f; do
  base="$(basename "$f")"
  case "$base" in
    .env.example|.env.sample|.env.template|.env.dist) ;;
    .env|.env.*) sus env "$f";;
    *.pem|*.key|*.p12|*.pfx|*.jks|*.keystore|id_rsa|id_rsa.*|id_ed25519|id_ed25519.*|id_ecdsa|id_ecdsa.*) sus key "$f";;
    .DS_Store) sus ds-store "$f";;
  esac
  case "/$f/" in */node_modules/*) sus node_modules "$f";; esac
  nsha="$(awk '{print $4}' <<<"$meta")"
  size="$(g cat-file -s "$nsha" 2>/dev/null || echo 0)"
  [ "$size" -gt 512000 ] 2>/dev/null && sus large "$f ($((size / 1024))KB)"
done < <(g diff --raw -z --no-renames --diff-filter=d "$range_base" "$head")
secrets="$(g diff -U0 --no-renames --diff-filter=d "$range_base" "$head" | awk '
  /^\+\+\+ b\// { file = substr($0, 7); next }
  /^\+/ && ($0 ~ /-----BEGIN ([A-Z]+ )?PRIVATE KEY-----/ || $0 ~ /AKIA[0-9A-Z]{16}/ || $0 ~ /gh[pousr]_[A-Za-z0-9]{36}/ || $0 ~ /xox[baprs]-[A-Za-z0-9-]{10,}/ || $0 ~ /sk-[A-Za-z0-9]{32,}/) \
    { if (!seen[file]++) print "SUSPICIOUS secret-like " file }')"
[ -n "$secrets" ] && { echo "$secrets"; flags=$((flags + $(wc -l <<<"$secrets"))); }
echo "FLAGS $flags"
exit 0
