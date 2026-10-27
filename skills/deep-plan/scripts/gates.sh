#!/usr/bin/env bash
# Usage: gates.sh <dir> [--only name,...] [--pinned <file>] [--logs <dir>]
# Runs every quality gate of the repo at <dir> in one call, one after another, and prints one line
# per gate, then the last 40 lines of each failing gate. Full logs go to <logs>/<name>.log
# (default $TMPDIR/gates/<repo>-<time>). Exit 1 when any gate failed, 2 on a bad argument,
# 3 when no gate exists. Output:
#   LOGS <dir>
#   PASS <name> [<n> tests] <seconds>s
#   FAIL <name> <seconds>s (log: <file>)
#   WARN <text>
#   --- <name>: last 40 lines            then the lines, indented, per failing gate
# Gates come from the pinned file when it exists: --pinned <file>, else <dir>/.deep-plan/contract.cmds.
# One gate per line, `<name>: <command>`; blank lines and #-comments are skipped; each command runs
# in <dir> through `bash -c`, so `cd sub && cmd` works. Otherwise they're detected from the repo:
#   package.json scripts  test, lint, typecheck (typecheck|check-types|type-check), format
#                         (format:check|prettier:check|format-check|check-format), coverage
#                         (coverage|test:coverage), run with the lockfile's package manager
#   pom.xml               test (mvnw or mvn)        build.gradle[.kts]  test (gradlew or gradle)
#   Package.swift         build, test
# --only runs just those gates, still in gate order; an unknown name exits 2.
set -uo pipefail

[ $# -ge 1 ] || { echo "Usage: gates.sh <dir> [--only name,...] [--pinned <file>] [--logs <dir>]" >&2; exit 2; }
dir="$(cd "$1" && pwd)"; shift
only=""; pinned="$dir/.deep-plan/contract.cmds"; logs=""
while [ $# -gt 0 ]; do
  case "$1" in
    --only) only="${2:-}"; shift 2;;
    --pinned) pinned="${2:-}"; shift 2;;
    --logs) logs="${2:-}"; shift 2;;
    *) echo "unknown argument $1" >&2; exit 2;;
  esac
done
repo="$(basename "$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || echo "$dir")")"
tmp="${TMPDIR:-/tmp}"; logs="${logs:-${tmp%/}/gates/$repo-$(date +%H%M%S)}"; mkdir -p "$logs"
export CI=true NO_COLOR=1 FORCE_COLOR=0

# Plain bash doesn't get the lazy nvm wrapper from .zshrc.
use_node() {
  export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  PATH="$PATH:/opt/homebrew/bin"
  local want; want="$(cat "$dir/.nvmrc" 2>/dev/null || true)"
  [ -n "$want" ] && command -v nvm >/dev/null 2>&1 && nvm use --silent "$want" >/dev/null 2>&1
  return 0
}
# Maven on the newest JDK can crash its plugins, so use the one the pom targets.
use_jdk() {
  local want home; want="$(sed -n 's:.*<java.version>\(.*\)</java.version>.*:\1:p' "$dir/pom.xml" | head -1)"
  [ -z "$want" ] && return 0
  home="$(/usr/libexec/java_home -v "$want" 2>/dev/null || true)"
  [ -z "$home" ] && home="$(ls -d "$HOME"/.sdkman/candidates/java/"$want".* 2>/dev/null | head -1)"
  [ -n "$home" ] && { export JAVA_HOME="$home"; export PATH="$JAVA_HOME/bin:$PATH"; }
  return 0
}

names=(); cmds=()
add() { names+=("$1"); cmds+=("$2"); }

if [ -f "$pinned" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*|[[:space:]]*'#'*) continue;; esac
    n="${line%%:*}"; c="${line#*:}"; n="$(xargs <<<"$n")"; c="${c# }"
    [[ "$line" == *:* ]] && [ -n "$n" ] && [ -n "$c" ] && add "$n" "$c"
  done < "$pinned"
else
  if [ -f "$dir/package.json" ]; then
    use_node
    pm=npm; [ -f "$dir/pnpm-lock.yaml" ] && pm=pnpm; [ -f "$dir/yarn.lock" ] && pm=yarn
    { [ -f "$dir/bun.lock" ] || [ -f "$dir/bun.lockb" ]; } && pm=bun
    command -v "$pm" >/dev/null 2>&1 || { [ "$pm" = pnpm ] && pm="corepack pnpm"; }
    scripts="$(python3 -c 'import json,sys; [print(k+"\t"+v) for k,v in json.load(open(sys.argv[1])).get("scripts",{}).items()]' "$dir/package.json" 2>/dev/null || true)"
    # pick <gate> <script>...: the first script that exists
    pick() { local gate="$1" s body; shift
      for s in "$@"; do
        body="$(awk -F'\t' -v s="$s" '$1==s{print $2; exit}' <<<"$scripts")"
        [ -z "$body" ] && continue
        grep -q 'no test specified' <<<"$body" && continue
        add "$gate" "$pm run $s"; return
      done; }
    pick test test
    pick lint lint
    pick typecheck typecheck check-types type-check
    pick format format:check prettier:check format-check check-format
    pick coverage coverage test:coverage
    [ -d "$dir/node_modules" ] || [ ${#names[@]} -eq 0 ] || echo "WARN node_modules is missing in $dir; install the dependencies first"
  fi
  if [ -f "$dir/pom.xml" ]; then
    mvn=mvn; [ -x "$dir/mvnw" ] && mvn=./mvnw
    add test "$mvn -B -ntp test"
  fi
  if [ -f "$dir/build.gradle" ] || [ -f "$dir/build.gradle.kts" ]; then
    gradle=gradle; [ -x "$dir/gradlew" ] && gradle=./gradlew
    add test "$gradle test --console=plain"
  fi
  if [ -f "$dir/Package.swift" ]; then
    add build "swift build"
    add test "swift test"
  fi
fi

if [ ${#names[@]} -eq 0 ]; then
  echo "NONE no gates found in $dir: no $pinned, package.json scripts, pom.xml, build.gradle or Package.swift"; exit 3
fi
if [ -n "$only" ]; then
  for want in ${only//,/ }; do
    printf '%s\n' "${names[@]}" | grep -qx -- "$want" || { echo "unknown gate $want (have: ${names[*]})" >&2; exit 2; }
  done
fi
[ -f "$dir/pom.xml" ] && use_jdk

# count_tests <log>: the test total the runner reported, or nothing.
count_tests() {
  local clean n; clean="$(sed $'s/\x1b\\[[0-9;]*m//g' "$1")"
  # Maven prints a total per module; the per-class lines carry " - in ".
  n="$(grep -E '^\[[A-Z]+\] Tests run: [0-9]+' <<<"$clean" | grep -v ' - in ' | sed -E 's/.*Tests run: ([0-9]+).*/\1/' | paste -sd+ - | bc 2>/dev/null)"
  # vitest: "Tests  1 failed | 293 passed (294)"
  [ -z "$n" ] || [ "$n" = 0 ] && n="$(grep -E '^ *Tests +[0-9]' <<<"$clean" | sed -E -n 's/.*\(([0-9]+)\)\s*$/\1/p' | paste -sd+ - | bc 2>/dev/null)"
  # jest: "Tests:  1 failed, 293 passed, 294 total"
  [ -z "$n" ] || [ "$n" = 0 ] && n="$(grep -E '^ *Tests: ' <<<"$clean" | sed -E -n 's/.* ([0-9]+) total.*/\1/p' | paste -sd+ - | bc 2>/dev/null)"
  # swift test: "Executed 12 tests, with 0 failures" (the last line is the total); swift-testing: "Test run with 12 tests"
  [ -z "$n" ] || [ "$n" = 0 ] && n="$(grep -E '^ *Executed [0-9]+ tests?' <<<"$clean" | tail -1 | sed -E 's/.*Executed ([0-9]+) test.*/\1/')"
  [ -z "$n" ] || [ "$n" = 0 ] && n="$(grep -E 'Test run with [0-9]+ tests?' <<<"$clean" | tail -1 | sed -E 's/.*Test run with ([0-9]+) test.*/\1/')"
  # pytest: "=== 12 passed, 1 failed in 0.3s ==="
  [ -z "$n" ] || [ "$n" = 0 ] && n="$(grep -E '^=+ .*(passed|failed)' <<<"$clean" | tail -1 | grep -oE '[0-9]+ (passed|failed)' | cut -d' ' -f1 | paste -sd+ - | bc 2>/dev/null)"
  [ -n "$n" ] && [ "$n" != 0 ] && echo "$n"
  return 0
}

echo "LOGS $logs"
failed=0; fails=()
for i in "${!names[@]}"; do
  name="${names[$i]}"
  [ -n "$only" ] && ! grep -qx -- "$name" < <(tr ',' '\n' <<<"$only") && continue
  log="$logs/$name.log"; start=$SECONDS
  if (cd "$dir" && bash -c "${cmds[$i]}") >"$log" 2>&1 </dev/null; then
    n="$(count_tests "$log")"
    echo "PASS $name${n:+ $n tests} $((SECONDS - start))s"
  else
    failed=1; fails+=("$name")
    echo "FAIL $name $((SECONDS - start))s (log: $log)"
  fi
done
for name in ${fails[@]+"${fails[@]}"}; do
  echo "--- $name: last 40 lines"
  sed $'s/\x1b\\[[0-9;]*m//g' "$logs/$name.log" | tail -n 40 | sed 's/^/  /'
done
exit $failed
