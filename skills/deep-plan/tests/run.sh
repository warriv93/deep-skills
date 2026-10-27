#!/usr/bin/env bash
# Usage: tests/run.sh
# Runs scripts/gates.sh and scripts/review-pack.sh against throwaway fixture repos and asserts on its output lines.
# Prints PASS/FAIL per assertion and exits non-zero on any FAIL.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
G="$here/scripts/gates.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=$((fails+1)); }
has() { if grep -qE -- "$2" <<<"$3"; then pass "$1"; else fail "$1"; echo "  wanted /$2/ in:"; sed 's/^/  | /' <<<"$3"; fi; }
hasnt() { if grep -qE -- "$2" <<<"$3"; then fail "$1"; echo "  unwanted /$2/ in:"; sed 's/^/  | /' <<<"$3"; else pass "$1"; fi; }

for f in "$here"/scripts/*.sh; do bash -n "$f" && pass "syntax $(basename "$f")" || fail "syntax $(basename "$f")"; done

n="$T/npm"; mkdir -p "$n"; git -C "$n" init -q
cat > "$n/package.json" <<'J'
{"scripts":{"test":"echo '      Tests  1 failed | 293 passed (294)'","lint":"for i in $(seq 1 60); do echo line $i; done; exit 1","check-types":"true","prettier:check":"true"}}
J
out="$("$G" "$n" --logs "$T/l1" 2>&1)"; rc=$?
has   "gates: a passing gate prints its test count" '^PASS test 294 tests [0-9]+s' "$out"
has   "gates: a failing gate names its log" "^FAIL lint [0-9]+s \(log: $T/l1/lint.log\)" "$out"
has   "gates: aliases map to the canonical names" '^PASS typecheck .*' "$out"
has   "gates: format comes from prettier:check" '^PASS format ' "$out"
has   "gates: only the last 40 lines of a failure" '^  line 60$' "$out"
hasnt "gates: older lines are cut" '^  line 20$' "$out"
[ $rc = 1 ] && pass "gates: exit 1 when a gate fails" || fail "gates: exit 1 when a gate fails (got $rc)"
[ -f "$T/l1/lint.log" ] && grep -q 'line 1$' "$T/l1/lint.log" && pass "gates: the full log is on disk" || fail "gates: the full log is on disk"

out="$("$G" "$n" --only test,typecheck --logs "$T/l2" 2>&1)"; rc=$?
hasnt "gates: --only skips the other gates" '^(PASS|FAIL) (lint|format)' "$out"
[ $rc = 0 ] && pass "gates: exit 0 when the chosen gates pass" || fail "gates: exit 0 when the chosen gates pass (got $rc)"
out="$("$G" "$n" --only nope 2>&1)"; rc=$?
[ $rc = 2 ] && has "gates: an unknown gate exits 2" 'unknown gate nope' "$out" || fail "gates: an unknown gate exits 2 (got $rc)"

printf '# pinned\nunit: echo "Tests: 4 passed, 5 total"\nbad: echo oops && false\n' > "$T/p.cmds"
out="$("$G" "$n" --pinned "$T/p.cmds" --logs "$T/l3" 2>&1)"
has   "gates: pinned file replaces detection" '^PASS unit 5 tests' "$out"
hasnt "gates: pinned file replaces detection (no lint)" '^(PASS|FAIL) lint' "$out"
has   "gates: a failing pinned gate shows its output" '^  oops$' "$out"

e="$T/empty"; mkdir -p "$e"; git -C "$e" init -q
out="$("$G" "$e" 2>&1)"; rc=$?
[ $rc = 3 ] && has "gates: a repo with no gates exits 3" '^NONE' "$out" || fail "gates: a repo with no gates exits 3 (got $rc)"

# mkrepo <dir>: a git repo with one empty commit on main, quiet identity.
mkrepo() { mkdir -p "$1"; git -C "$1" init -q -b main; git -C "$1" config user.email t@t; git -C "$1" config user.name t
  git -C "$1" commit -q --allow-empty -m base; }
put() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }
commit() { git -C "$1" add -A; git -C "$1" commit -q -m "$2"; }

# ---------- review-pack.sh
p="$T/repos/pack-fixture"; mkrepo "$p"
put "$p/src/a.ts" 'one
two
three'
put "$p/src/old name.ts" 'keep
keep
keep
keep
keep'
put "$p/package-lock.json" '{}'
printf '\211PNG\000\001' > "$p/logo.png"
commit "$p" fixture
git -C "$p" mv "src/old name.ts" "src/new name.ts"
put "$p/src/a.ts" 'one
2
three'
put "$p/package-lock.json" '{"x":1}'
printf '\211PNG\000\002' > "$p/logo.png"
put "$p/src/__snapshots__/a.snap" 'snap'
put "$p/dist/bundle.js" 'x'
put "$p/lib/app.min.js" 'x'
put "$p/src/untracked.ts" 'fresh'
commit "$p" change
put "$p/src/a.ts" 'one
2
3'
put "$p/src/loose.ts" 'loose
file'
git -C "$p" tag base HEAD~1
out="$("$here/scripts/review-pack.sh" "$p" base HEAD "$T/pack1" 2>&1)"
has  "pack: a changed file gets its own diff" '^\+1 -1 src/a.ts → .*/diff/src/a.ts.diff' "$out"
has  "pack: a rename with an edit is one line" 'src/new name.ts' "$out"
has  "pack: lockfile skipped" '^SKIPPED lockfile package-lock.json' "$out"
has  "pack: binary skipped" '^SKIPPED binary logo.png' "$out"
has  "pack: snapshot skipped" '^SKIPPED snapshot src/__snapshots__/a.snap' "$out"
has  "pack: generated skipped" '^SKIPPED generated dist/bundle.js' "$out"
has  "pack: minified skipped" '^SKIPPED minified lib/app.min.js' "$out"
has  "pack: totals count skipped files" '^TOTAL 8 files .*\(3 to review, 5 skipped\)' "$out"
hasnt "pack: skipped files get no diff" 'package-lock.json.diff|logo.png.diff' "$(cd "$T/pack1" && find diff -type f)"
has  "pack: stat.txt covers skipped files too" 'logo.png' "$(cat "$T/pack1/stat.txt")"
has  "pack: committed head ignores uncommitted edits" '^\+1 -1 src/a.ts' "$out"
out="$("$here/scripts/review-pack.sh" "$p" base WORKTREE "$T/pack2" 2>&1)"
has  "pack: WORKTREE counts the uncommitted edit" '^\+2 -2 src/a.ts' "$out"
has  "pack: WORKTREE counts untracked files" '^\+2 -0 src/loose.ts → .*/diff/src/loose.ts.diff' "$out"
has  "pack: untracked diff is a new-file diff" '^\+loose' "$(cat "$T/pack2/diff/src/loose.ts.diff")"
out="$("$here/scripts/review-pack.sh" "$p" base base "$T/pack3" 2>&1)"
has  "pack: empty change says 0 files" '^TOTAL 0 files' "$out"
out="$("$here/scripts/review-pack.sh" "$p" nope HEAD "$T/pack4" 2>&1 || true)"
has  "pack: unknown base fails" 'unknown base ref' "$out"

echo
[ "$fails" = 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
