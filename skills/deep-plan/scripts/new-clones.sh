#!/usr/bin/env bash
# Usage: new-clones.sh <dir> <base-ref> [jscpd option...]
# Fails only on copy-pasted code that <dir>'s working tree has and <base-ref>'s tree doesn't, so
# duplication the base already holds never blocks. Runs jscpd (>= 5.2, which has --baseline-from-ref;
# $JSCPD overrides the command) over <dir>, honouring its .gitignore and .jscpd.json. Exit 0 when no
# clone is new, 1 when one is, 2 on a bad argument or unknown ref; any other jscpd failure keeps its
# exit code and prints its last 40 lines. Output:
#   PASS no new clones against <base-ref>
#   Clone found (<format>) [NEW]      then its locations, per new clone
#   FIX <how to remove them>
set -uo pipefail

[ $# -ge 2 ] || { echo "Usage: new-clones.sh <dir> <base-ref> [jscpd option...]" >&2; exit 2; }
dir="$1"; ref="$2"; shift 2
git -C "$dir" rev-parse --verify -q "$ref^{commit}" >/dev/null \
  || { echo "unknown base ref $ref in $dir: fetch it, or pin the branch this work started from"; exit 2; }
jscpd="${JSCPD:-npx -y jscpd@^5.2.0}"

out="$(cd "$dir" && $jscpd . --baseline-from-ref "$ref" --fail-on-new-clones 0 --reporters console --no-tips "$@" 2>&1)"; rc=$?
out="$(sed $'s/\x1b\\[[0-9;]*m//g' <<<"$out")"
[ $rc = 0 ] && { echo "PASS no new clones against $ref"; exit 0; }

new="$(awk '/^Clone found .*\[NEW\]/{p=1; print; next} /^Clone found|^[^ ]/{p=0} p' <<<"$out")"
[ -n "$new" ] || { tail -n 40 <<<"$out"; exit $rc; }
echo "$new"
echo "FIX each clone above is new against $ref: move the shared code into one function or module that every copy calls, or call the one that already exists. A copy that must stay goes between // jscpd:ignore-start and // jscpd:ignore-end, with a comment giving the reason."
exit 1
