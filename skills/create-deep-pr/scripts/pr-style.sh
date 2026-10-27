#!/usr/bin/env bash
# Usage: pr-style.sh <repo dir> [--n 5]
# Summarises the style of the repo's last n merged PRs and prints the body of the one nearest the median length.
#   STYLE n=<n> median=<lines> lines; sections <heading> <k>/<n> ...; checklists <k>/<n>; links <k>/<n>
#   EXAMPLE #<number>, then that PR's body
# Prints "STYLE n=0" when the repo has no merged PRs.
set -euo pipefail

repo="${1:?usage: pr-style.sh <repo dir> [--n 5]}"
n=5
[ "${2:-}" = "--n" ] && n="${3:?--n needs a number}"

prs="$(cd "$repo" && gh pr list --state merged --limit "$n" --json number,title,body)"

jq -r '
  def lines: (.body // "" | gsub("\r"; "") | split("\n") | length);
  def headings: [(.body // "" | gsub("\r"; "") | split("\n")[] | select(test("^#{1,6} ")) | sub("^#+ +"; "") | gsub("\\s+$"; ""))] | unique;
  length as $n
  | if $n == 0 then "STYLE n=0" else
    ([.[] | lines] | sort) as $l
    | (if $n % 2 == 1 then $l[($n - 1) / 2] else ($l[$n / 2 - 1] + $l[$n / 2]) / 2 | floor end) as $median
    | ([.[] | headings[]] | group_by(.) | map({h: .[0], k: length}) | sort_by(-.k, .h) | .[:8]
        | map("\(.h) \(.k)/\($n)") | join(", ")) as $sections
    | ([.[] | select((.body // "") | test("- \\[[ xX]\\]"))] | length) as $checks
    | ([.[] | select((.body // "") | test("\\]\\(http"))] | length) as $links
    | (sort_by([((lines - $median) | fabs), -.number])[0]) as $pick
    | "STYLE n=\($n) median=\($median) lines; sections \($sections); checklists \($checks)/\($n); links \($links)/\($n)",
      "EXAMPLE #\($pick.number)",
      ($pick.body // "")
    end
' <<<"$prs"
