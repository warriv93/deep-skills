#!/usr/bin/env bash
# Usage: review-pack.sh <repo-or-worktree> <base> <head> <out-dir>
# The change as one diff file per path, so each reviewer reads an index and then only the diffs
# its axis needs, instead of running `git diff` again. <base> is any ref; the diff starts at its
# merge base with <head>. <head> is a ref, or WORKTREE for the working tree, which also counts
# the untracked files. Writes:
#   <out-dir>/stat.txt           the whole change as `git diff --stat`, skipped files included
#   <out-dir>/diff/<path>.diff   one diff per reviewable file
#   <out-dir>/index.txt          the lines below
# Prints the index, one machine-readable line per fact:
#   PACK base=<sha> head=<sha|WORKTREE> dir=<out-dir>
#   +<added> -<deleted> <path> → <diff file>     a file to review (a rename names its new path)
#   SKIPPED <reason> <path>                      reason: binary, image, lockfile, generated,
#                                                minified, snapshot, font, archive; no diff file
#   TOTAL <n> files +<added> -<deleted> (<m> to review, <k> skipped)
# Never writes outside <out-dir>. Exit 2 on a bad argument.
set -euo pipefail

[ $# -eq 4 ] || { echo "Usage: review-pack.sh <repo-or-worktree> <base> <head> <out-dir>" >&2; exit 2; }
root="$(cd "$1" && git rev-parse --show-toplevel)"; out="$4"
g() { git -C "$root" --literal-pathspecs -c core.quotePath=false "$@"; }
base="$(g merge-base "$2" HEAD)" || { echo "unknown base ref $2" >&2; exit 2; }
if [ "$3" = WORKTREE ]; then head=WORKTREE; endrev=(); else
  head="$(g rev-parse --verify "$3^{commit}")" || { echo "unknown head $3" >&2; exit 2; }
  base="$(g merge-base "$2" "$head")"; endrev=("$head"); fi
rm -rf "$out"; mkdir -p "$out/diff"; out="$(cd "$out" && pwd)"
untracked=(); [ "$head" = WORKTREE ] && while IFS= read -r -d '' f; do untracked+=("$f"); done < <(g ls-files --others --exclude-standard -z)

# why_skip <path>: prints the reason this file gets no diff, or nothing.
why_skip() {
  local p="$1" lower; lower="$(tr '[:upper:]' '[:lower:]' <<<"$1")"
  case "$lower" in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.svg|*.ico|*.icns|*.bmp|*.heic|*.avif) echo image;;
    *.woff|*.woff2|*.ttf|*.otf|*.eot) echo font;;
    *.zip|*.gz|*.tgz|*.jar|*.war|*.pdf|*.mp4|*.mov|*.mp3|*.wasm|*.dylib|*.so|*.class) echo archive;;
    */package-lock.json|package-lock.json|*/pnpm-lock.yaml|pnpm-lock.yaml|*/yarn.lock|yarn.lock|*/bun.lock|bun.lock|*/bun.lockb|bun.lockb|\
*/cargo.lock|cargo.lock|*/gemfile.lock|gemfile.lock|*/poetry.lock|poetry.lock|*/uv.lock|uv.lock|*/package.resolved|package.resolved|\
*/podfile.lock|podfile.lock|*/go.sum|go.sum|*/composer.lock|composer.lock|*/gradle.lockfile|gradle.lockfile) echo lockfile;;
    *.min.js|*.min.css|*.min.mjs|*.js.map|*.css.map) echo minified;;
    */__snapshots__/*|__snapshots__/*|*/snapshots/*|snapshots/*|*/__image_snapshots__/*|*.snap) echo snapshot;;
    */generated/*|generated/*|*/dist/*|dist/*|*/build/*|build/*|*/target/*|target/*|*/node_modules/*|node_modules/*|*.generated.*|*_generated.*|*.pb.go|*.g.dart|*.freezed.dart) echo generated;;
  esac
}

: > "$out/index.body"; : > "$out/skipped.body"
files=0; rev=0; skipped=0; add_total=0; del_total=0
# emit <added> <deleted> <path> <old-path-or-empty> <untracked 0|1>
emit() {
  local a="$1" d="$2" p="$3" old="$4" untr="$5" why=""
  files=$((files+1))
  [ "$a" = - ] && why=binary
  [ -z "$why" ] && why="$(why_skip "$p")"
  if [ -n "$why" ]; then
    skipped=$((skipped+1)); echo "SKIPPED $why $p" >> "$out/skipped.body"; return
  fi
  rev=$((rev+1)); add_total=$((add_total+a)); del_total=$((del_total+d))
  mkdir -p "$out/diff/$(dirname "$p")"
  if [ "$untr" = 1 ]; then
    git -C "$root" diff --no-index -- /dev/null "$p" > "$out/diff/$p.diff" || true
  elif [ -n "$old" ]; then
    g diff -M "$base" ${endrev[@]+"${endrev[@]}"} -- "$old" "$p" > "$out/diff/$p.diff"
  else
    g diff "$base" ${endrev[@]+"${endrev[@]}"} -- "$p" > "$out/diff/$p.diff"
  fi
  echo "+$a -$d $p → $out/diff/$p.diff" >> "$out/index.body"
}

# Tracked changes: numstat -z gives `a<TAB>d<TAB>path\0`, or `a<TAB>d<TAB>\0old\0new\0` for a rename.
while IFS= read -r -d '' rec; do
  a="${rec%%$'\t'*}"; rest="${rec#*$'\t'}"; d="${rest%%$'\t'*}"; p="${rest#*$'\t'}"; old=""
  if [ -z "$p" ]; then IFS= read -r -d '' old; IFS= read -r -d '' p; fi
  emit "$a" "$d" "$p" "$old" 0
done < <(g diff -M --numstat -z "$base" ${endrev[@]+"${endrev[@]}"})
for f in ${untracked[@]+"${untracked[@]}"}; do
  ns="$(git -C "$root" diff --no-index --numstat -- /dev/null "$f" | head -1 || true)"
  emit "$(cut -f1 <<<"$ns")" "$(cut -f2 <<<"$ns")" "$f" "" 1
done

{ g diff -M --stat=120 "$base" ${endrev[@]+"${endrev[@]}"}
  for f in ${untracked[@]+"${untracked[@]}"}; do git -C "$root" diff --no-index --stat=120 -- /dev/null "$f" | sed '$d' || true; done; } > "$out/stat.txt"

{ echo "PACK base=$(g rev-parse --short "$base") head=$([ "$head" = WORKTREE ] && echo WORKTREE || echo "${head:0:7}") dir=$out"
  sort -k3 "$out/index.body"
  sort -k3 "$out/skipped.body"
  echo "TOTAL $files files +$add_total -$del_total ($rev to review, $skipped skipped)"; } | tee "$out/index.txt"
rm -f "$out/index.body" "$out/skipped.body"
