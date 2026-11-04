#!/usr/bin/env bash
# Usage: copilot-review.sh wait <pr-number> [timeout-seconds]
#        copilot-review.sh reply <pr-number> <comment-id> <body-file> [--resolve]
# Run inside the repo's checkout.
# wait: blocks until Copilot has reviewed the PR's current head (default timeout 900s), then prints
#   REVIEW <state> <count> comments
#   COMMENT <id> <path>:<line>     one per inline comment, followed by its body indented two spaces
# and exits 0. Prints TIMEOUT and exits 3 when no review arrives in time, and NOT_REQUESTED and
# exits 4 when Copilot is neither a requested reviewer nor has reviewed the head.
# reply: posts the body file as a reply in the comment's thread, and with --resolve resolves it.
set -euo pipefail

repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
owner="${repo%/*}"; name="${repo#*/}"

copilot_review_id() {
  gh api "repos/$repo/pulls/$1/reviews" --paginate \
    -q "[.[] | select((.user.login | test(\"copilot\"; \"i\")) and .commit_id == \"$2\")] | last | .id // empty"
}

copilot_requested() {
  gh api "repos/$repo/pulls/$1/requested_reviewers" -q '[.users[].login] | map(test("copilot"; "i")) | any'
}

wait_for_review() {
  local number="$1" timeout="${2:-900}" head review deadline
  head="$(gh pr view "$number" --json headRefOid -q .headRefOid)"
  deadline=$(( $(date +%s) + timeout ))
  while :; do
    review="$(copilot_review_id "$number" "$head")"
    [ -n "$review" ] && break
    if [ "$(copilot_requested "$number")" != "true" ]; then echo "NOT_REQUESTED"; exit 4; fi
    if [ "$(date +%s)" -ge "$deadline" ]; then echo "TIMEOUT"; exit 3; fi
    sleep 30
  done
  local state comments
  state="$(gh api "repos/$repo/pulls/$number/reviews/$review" -q .state)"
  comments="$(gh api "repos/$repo/pulls/$number/comments" --paginate -q ".[] | select(.pull_request_review_id == $review)" | jq -s .)"
  echo "REVIEW $state $(jq length <<<"$comments") comments"
  jq -r '.[] | "COMMENT \(.id) \(.path):\(.line // .original_line)", (.body | split("\n") | map("  " + .) | join("\n"))' <<<"$comments"
}

thread_of() {
  gh api graphql -F owner="$owner" -F name="$name" -F number="$1" -f query='
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) { pullRequest(number: $number) {
        reviewThreads(first: 100) { nodes { id comments(first: 1) { nodes { databaseId } } } } } } }' \
    -q ".data.repository.pullRequest.reviewThreads.nodes[] | select(.comments.nodes[0].databaseId == $2) | .id"
}

reply() {
  local number="$1" comment="$2" body="$3" resolve="${4:-}"
  gh api -X POST "repos/$repo/pulls/$number/comments/$comment/replies" -F body=@"$body" -q '"REPLIED \(.id)"'
  if [ "$resolve" = "--resolve" ]; then
    local thread; thread="$(thread_of "$number" "$comment")"
    gh api graphql -f query="mutation { resolveReviewThread(input: {threadId: \"$thread\"}) { thread { isResolved } } }" \
      -q '"RESOLVED \(.data.resolveReviewThread.thread.isResolved)"'
  fi
}

case "${1:-}" in
  wait) shift; wait_for_review "$@" ;;
  reply) shift; reply "$@" ;;
  *) sed -n '2,3p' "$0" >&2; exit 2 ;;
esac
