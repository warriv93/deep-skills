#!/usr/bin/env bash
# Usage: tests/run.sh
# Runs scripts/push-preview.sh against a throwaway repo with a local bare remote and asserts on
# its output lines. Prints PASS/FAIL per assertion and exits non-zero on any FAIL.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
P="$here/scripts/push-preview.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
fails=0
pass() { echo "PASS $1"; }
fail() { echo "FAIL $1"; fails=$((fails+1)); }
has() { if grep -qE -- "$2" <<<"$3"; then pass "$1"; else fail "$1"; echo "  wanted /$2/ in:"; sed 's/^/  | /' <<<"$3"; fi; }
hasnt() { if grep -qE -- "$2" <<<"$3"; then fail "$1"; echo "  unwanted /$2/ in:"; sed 's/^/  | /' <<<"$3"; else pass "$1"; fi; }
code() { if [ "$2" = "$3" ]; then pass "$1"; else fail "$1 (exit $3, wanted $2)"; fi; }

bash -n "$P" && pass "syntax push-preview.sh" || fail "syntax push-preview.sh"

git init -q --bare "$T/remote.git"
w="$T/work"; git clone -q "$T/remote.git" "$w" 2>/dev/null; cd "$w"
git config user.email me@x; git config user.name Me
git checkout -q -b main; echo a > a.txt; git add .; git commit -qm base; git push -q origin main; git remote set-head origin main 2>/dev/null
git checkout -q -b feat
mkdir -p src other; echo 1 > src/a.ts; git add src; GIT_AUTHOR_DATE="2026-10-13T08:00:00" git commit -qm "Old commit"
echo SECRET=1 > .env.local; echo x > other/.DS_Store; echo k > server.pem; head -c 700000 /dev/zero > big.bin
echo "-----BEGIN RSA PRIVATE KEY-----" > other/n.txt; echo ok > .env.example
git add -f .; git commit -qm "Add stuff"

out="$("$P" "$w" origin feat --paths src)"; rc=$?
code  "preview: exit 0 for a branch that can be pushed" 0 $rc
has   "preview: a new branch is named as new" '^TARGET origin/feat new \(base origin/main\)' "$out"
has   "preview: an old commit is flagged" '^COMMIT [0-9a-f]{7} Me Old commit FLAG older-than-newest' "$out"
has   "preview: a commit outside --paths is flagged" 'Add stuff FLAG outside-paths' "$out"
has   "preview: env file" '^SUSPICIOUS env \.env\.local' "$out"
hasnt "preview: .env.example is fine" 'SUSPICIOUS .*env\.example' "$out"
has   "preview: key file" '^SUSPICIOUS key server\.pem' "$out"
has   "preview: .DS_Store" '^SUSPICIOUS ds-store other/\.DS_Store' "$out"
has   "preview: large file" '^SUSPICIOUS large big\.bin' "$out"
has   "preview: private key in an added line" '^SUSPICIOUS secret-like other/n\.txt' "$out"
has   "preview: file totals" '^FILES 7 ' "$out"

git push -q origin feat
out="$("$P" "$w")"; rc=$?
code  "preview: nothing to push exits 0" 0 $rc
has   "preview: nothing to push says so" '^NOTHING' "$out"

echo 2 > src/b.ts; git add src; git commit -qm "Next"
out="$("$P" "$w")"
has   "preview: an existing branch counts its commits" '^TARGET origin/feat existing \(1 ahead\)' "$out"
hasnt "preview: a clean push has no flags" 'FLAG |SUSPICIOUS' "$out"

git clone -q "$T/remote.git" "$T/other" 2>/dev/null; (cd "$T/other"; git config user.email o@o; git config user.name O
  git checkout -q feat; echo 5 > e.txt; git add .; git commit -qm remote-only; git push -q origin feat)
out="$("$P" "$w")"; rc=$?
code  "preview: diverged exits 2" 2 $rc
has   "preview: diverged is named" '^BLOCKED diverged \(1 behind, 1 ahead\)' "$out"
git reset -q --hard HEAD~1
out="$("$P" "$w")"; rc=$?
code  "preview: behind exits 2" 2 $rc
has   "preview: behind is named" '^BLOCKED behind' "$out"

echo
[ "$fails" = 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
