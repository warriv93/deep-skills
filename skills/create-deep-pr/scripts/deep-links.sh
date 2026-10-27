#!/usr/bin/env bash
# Usage: deep-links.sh <owner/repo> <pr-number> <path[:line[:L]]>...
# Prints one line per argument: LINK <path[:line]> <url>, a link into the PR's diff on GitHub.
# GitHub anchors each file at #diff-<sha256 of its path>; R<line> is a line in the new file,
# L<line> (pass path:line:L) a line in the old one, for removed code. No line → the file's header.
set -euo pipefail
[ $# -ge 3 ] || { echo "usage: deep-links.sh <owner/repo> <pr-number> <path[:line[:L]]>..." >&2; exit 2; }
slug="$1" n="$2"; shift 2
for arg in "$@"; do
  IFS=: read -r path line side <<<"$arg"
  hash="$(printf '%s' "$path" | shasum -a 256 | cut -c1-64)"
  url="https://github.com/$slug/pull/$n/changes#diff-$hash"
  [ -n "${line:-}" ] && url="$url${side:-R}$line"
  echo "LINK $path${line:+:$line} $url"
done
