#!/usr/bin/env bash
# Usage: tests/run.sh
# Runs scripts/gates.sh, scripts/review-pack.sh, scripts/new-clones.sh and scripts/land.sh against throwaway fixture repos and asserts on its output lines.
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

h="$T/l3/gates.jsonl"
has   "history: one line per gate run" '^2$' "$(wc -l < "$h" | tr -d ' ')"
has   "history: a passing run is ok" '"gate": "unit", "ok": true, "secs": [0-9]+, "sha": null' "$(cat "$h")"
has   "history: a failing run is not ok" '"gate": "bad", "ok": false' "$(cat "$h")"
has   "history: each run says when in UTC" '^\{"at": "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"' "$(head -1 "$h")"
git -C "$n" -c user.email=t@t -c user.name=t commit -q --allow-empty -m one
"$G" "$n" --pinned "$T/p.cmds" --logs "$T/l3" --only unit >/dev/null 2>&1
has   "history: a rerun appends instead of overwriting" '^3$' "$(wc -l < "$h" | tr -d ' ')"
has   "history: a run on a commit carries its sha" "\"sha\": \"$(git -C "$n" rev-parse HEAD)\"}$" "$(tail -1 "$h")"
printf 'say "hi" \\ there: true\n' > "$T/q.cmds"
"$G" "$n" --pinned "$T/q.cmds" --logs "$T/l5" >/dev/null 2>&1
python3 -c 'import json,sys; [json.loads(l) for l in open(sys.argv[1])]' "$T/l5/gates.jsonl" 2>/dev/null \
  && pass "history: a gate name with quotes stays valid JSON" || fail "history: a gate name with quotes stays valid JSON"
mkdir -p "$T/l6/gates.jsonl"
out="$("$G" "$n" --pinned "$T/p.cmds" --logs "$T/l6" 2>&1)"; rc=$?
[ $rc = 1 ] && pass "history: an unwritable history keeps the exit code" || fail "history: an unwritable history keeps the exit code (got $rc)"
has   "history: an unwritable history keeps the gate lines" '^PASS unit' "$out"
hasnt "history: an unwritable history prints no error" 'gates\.jsonl' "$out"
out="$(TMPDIR="$T/tmp" "$G" "$n" --pinned "$T/p.cmds" 2>&1)"
[ -z "$(find "$T/tmp" -name gates.jsonl)" ] && pass "history: none without --logs" || fail "history: none without --logs"

mkdir -p "$n/.deep-plan/archive/M1"; cp "$T/p.cmds" "$n/.deep-plan/archive/M1/contract.cmds"
out="$("$G" "$n" --only typecheck --logs "$T/l4" 2>&1)"
has   "gates: detection warns when the contract was archived" '^WARN .*\.deep-plan/archive/M1/contract\.cmds' "$out"
rm -rf "$n/.deep-plan"

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

# ---------- new-clones.sh, with jscpd stubbed by $JSCPD
C="$here/scripts/new-clones.sh"
c="$T/repos/clones"; mkrepo "$c"
stub() { printf '#!/usr/bin/env bash\necho "$*" > %q\ncat %q\nexit %s\n' "$T/stub.args" "$T/stub.out" "$1" > "$T/jscpd"; chmod +x "$T/jscpd"; }
printf '\033[1mClone found (typescript)\033[22m\n - a.ts [1:1 - 7:2] (7 lines)\n   b.ts [1:1 - 7:2]\nClone found (typescript) [NEW]\n - a.ts [1:1 - 7:2] (7 lines)\n   c.ts [1:1 - 7:2]\n+----+\nFound 2 clones (1 new).\nERROR: jscpd found 1 new clones\n' > "$T/stub.out"
stub 1; out="$(JSCPD="$T/jscpd" "$C" "$c" main 2>&1)"; rc=$?
[ $rc = 1 ] && pass "clones: exit 1 on a new clone" || fail "clones: exit 1 on a new clone (got $rc)"
has   "clones: a new clone is shown with its locations" '^   c\.ts ' "$out"
hasnt "clones: a clone the base has is left out" 'b\.ts' "$out"
has   "clones: the failure names the fix" '^FIX .*against main' "$out"
has   "clones: jscpd compares against the base ref" '--baseline-from-ref main --fail-on-new-clones 0' "$(cat "$T/stub.args")"
stub 0; out="$(JSCPD="$T/jscpd" "$C" "$c" main 2>&1)"; rc=$?
[ $rc = 0 ] && has "clones: no new clone passes" '^PASS no new clones against main' "$out" || fail "clones: no new clone passes (got $rc)"
printf 'error: bad config\n' > "$T/stub.out"
stub 2; out="$(JSCPD="$T/jscpd" "$C" "$c" main 2>&1)"; rc=$?
[ $rc = 2 ] && has "clones: another jscpd failure keeps its output" '^error: bad config' "$out" || fail "clones: another jscpd failure keeps its exit code (got $rc)"
out="$(JSCPD="$T/jscpd" "$C" "$c" nope 2>&1)"; rc=$?
[ $rc = 2 ] && has "clones: an unknown base ref exits 2" 'unknown base ref nope' "$out" || fail "clones: an unknown base ref exits 2 (got $rc)"

# ---------- land.sh, with the gates pinned in each fixture's .deep-plan/contract.cmds
L="$here/scripts/land.sh"
# landfix <dir> <gate command>: main with a.txt, branch feat holding a story merge and its own commit; main moved on
landfix() { mkrepo "$1"; put "$1/.deep-plan/contract.cmds" "unit: $2"; put "$1/a.txt" one; commit "$1" a
  git -C "$1" switch -q -c feat; git -C "$1" switch -q -c story; put "$1/b.txt" b; commit "$1" b
  git -C "$1" switch -q feat; git -C "$1" merge -q --no-ff -m "merge story" story; put "$1/c.txt" c; commit "$1" c
  git -C "$1" switch -q main; put "$1/d.txt" d; commit "$1" d; }
trees() { git -C "$1" worktree list | wc -l | tr -d ' '; }

r="$T/land-ok"; landfix "$r" true; mkdir "$r/node_modules"; git -C "$r" switch -q --detach
out="$("$L" "$r" feat 2>&1)"; rc=$?
has   "land: lands the branch on main" "^LANDED main $(git -C "$r" rev-parse --short main)$" "$out"
has   "land: runs the gates" '^PASS unit' "$out"
has   "land: next is the push preview" '^NEXT .*push-preview\.sh .* origin main' "$out"
[ $rc = 0 ] && pass "land: exit 0 when landed" || fail "land: exit 0 when landed (got $rc)"
[ "$(git -C "$r" rev-list --merges main | wc -l | tr -d ' ')" = 0 ] && pass "land: merge commits flattened" || fail "land: merge commits flattened"
[ "$(git -C "$r" log --format=%s main | tr '\n' ' ')" = "c b d a base " ] && pass "land: the branch's commits sit on main" || fail "land: the branch's commits sit on main"
[ "$(git -C "$r" rev-parse feat)" = "$(git -C "$r" rev-parse main)" ] && pass "land: the branch moves to the landed commits" || fail "land: the branch moves to the landed commits"
[ "$(trees "$r")" = 1 ] && pass "land: the temporary worktree is gone" || fail "land: the temporary worktree is gone"
out="$("$L" "$r" feat 2>&1)"
has   "land: a landed branch has nothing to land" '^NOTHING feat is already in main' "$out"

r="$T/land-ff"; landfix "$r" true; put "$r/scratch.txt" x
out="$("$L" "$r" feat 2>&1)"
has   "land: base checked out fast-forwards there" '^LANDED main ' "$out"
[ "$(git -C "$r" rev-parse HEAD)" = "$(git -C "$r" rev-parse main)" ] && [ -f "$r/c.txt" ] && pass "land: the checkout has the landed tree" || fail "land: the checkout has the landed tree"
[ -f "$r/scratch.txt" ] && pass "land: untracked files stay" || fail "land: untracked files stay"

r="$T/land-dirty"; landfix "$r" true; put "$r/a.txt" edited; before="$(git -C "$r" rev-parse main)"
out="$("$L" "$r" feat 2>&1)"; rc=$?
has   "land: refuses a dirty checkout of the base" "^DIRTY .*/land-dirty: main is checked out there" "$out"
[ $rc = 1 ] && [ "$(git -C "$r" rev-parse main)" = "$before" ] && pass "land: dirty leaves main where it was" || fail "land: dirty leaves main where it was (rc $rc)"

r="$T/land-red"; landfix "$r" "echo broken && false"; git -C "$r" switch -q --detach; before="$(git -C "$r" rev-parse main)"
out="$("$L" "$r" feat 2>&1)"; rc=$?
has   "land: failing gates name the gate and keep the worktree" '^GATES-FAILED unit KEPT /' "$out"
has   "land: failing gates show their tail" '^  broken$' "$out"
kept="$(sed -n 's/^GATES-FAILED .* KEPT //p' <<<"$out")"
[ $rc = 1 ] && [ -d "$kept" ] && [ "$(git -C "$r" rev-parse main)" = "$before" ] && pass "land: red gates move nothing" || fail "land: red gates move nothing (rc $rc)"

r="$T/land-conflict"; landfix "$r" true; git -C "$r" switch -q feat; put "$r/a.txt" theirs; commit "$r" fa
git -C "$r" switch -q main; put "$r/a.txt" ours; commit "$r" ma; git -C "$r" switch -q --detach; before="$(git -C "$r" rev-parse main)"
out="$("$L" "$r" feat 2>&1)"; rc=$?
has   "land: a conflict names its files" '^CONFLICT a\.txt$' "$out"
[ $rc = 1 ] && [ "$(trees "$r")" = 1 ] && [ "$(git -C "$r" rev-parse main)" = "$before" ] && pass "land: a conflict aborts and cleans up" || fail "land: a conflict aborts and cleans up (rc $rc)"

r="$T/land-busy"; landfix "$r" true; git -C "$r" switch -q --detach; git -C "$r" worktree add -q "$T/land-busy-feat" feat; old="$(git -C "$r" rev-parse feat)"
out="$("$L" "$r" feat 2>&1)"
has   "land: lands a branch another worktree has checked out" '^LANDED main ' "$out"
[ "$(git -C "$r" rev-parse feat)" = "$old" ] && pass "land: leaves a checked-out branch where it is" || fail "land: leaves a checked-out branch where it is"
out="$("$L" "$r" nope 2>&1)"; rc=$?
[ $rc = 2 ] && has "land: an unknown branch exits 2" 'no branch nope' "$out" || fail "land: an unknown branch exits 2 (got $rc)"

echo
[ "$fails" = 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
