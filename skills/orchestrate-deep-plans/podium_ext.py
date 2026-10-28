"""orchestrate-deep-plans' verbs for the `podium` command: approve, commits, merge, prs, backfill, breakdown, brief,
launch, land, peek, turn, and handoff, which writes the prompts that hand planning, the quality gate and a retro to a
subagent.

`podium init --name orchestrate-deep-plans --command /orchestrate-deep-plans --extension <this file>` names it in
a run's podium.json. Git commands run in the repo, the run directory's parent. The story prompt is
phase-3-build.md's, next to this file.
"""
import glob
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

from podium_dashboard import human, sync
from podium_dashboard.commands import apply_set, cmd_status, require_owner, split_flags
from podium_dashboard.files import git_argv, write_atomic
from podium_dashboard.state import NOW, checkout_path, http, podium_dir, podium_url, queued_requests

UTC = lambda epoch: datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
GENERATED = {"planned", "commit", "landed"}
DISPATCHERS = ("paseo", "agent")
CLOSED = ("done", "dropped", "moved")


def configured_findings_remote():
    try:
        with open(os.path.expanduser("~/.podium/improve.json")) as fh:
            return json.load(fh).get("findings") or None
    except (OSError, ValueError, AttributeError):
        return None


FINDINGS_REMOTE = configured_findings_remote()
PHASE_3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "phase-3-build.md")


def checkout(p, path):
    """A path podium.json records for a checkout, `~`-based or relative to the run dir, as an absolute path; refused
    inside the run dir outside repos/ and worktrees/, where a pull may have written it."""
    if not path:
        return None
    full = checkout_path(p, path)
    if not full:
        sys.exit(f"refused checkout {path}: in the run dir outside repos/ and worktrees/")
    return full


ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
REPO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
SHA = re.compile(r"^[0-9a-f]{4,64}$")
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/\[\]-]{0,127}$")
PASEO_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")


def safe_id(x):
    """A milestone's or story's id from podium.json, once it is safe as a path component; refused otherwise."""
    if not (isinstance(x, str) and ID.fullmatch(x)):
        sys.exit(f"refused id {x!r}: not 1-32 letters, digits, _ or -")
    return x


def repo_name(x):
    """A repo name from podium.json, once it is a plain name and no path; refused otherwise."""
    if not (isinstance(x, str) and REPO.fullmatch(x)) or x in (".", ".."):
        sys.exit(f"refused repo {x!r}: not a plain name")
    return x


def branch_name(x):
    """A branch from podium.json, once git takes it as a branch name and never as an option; refused otherwise."""
    if not (isinstance(x, str) and x[:1] not in ("", "-") and "\0" not in x
            and not subprocess.run(git_argv("check-ref-format", f"refs/heads/{x}"), capture_output=True).returncode):
        sys.exit(f"refused branch {x!r}: not a branch name")
    return x


def commit_sha(x):
    """A commit sha from podium.json, once it is 4-64 hex digits; refused otherwise."""
    if not (isinstance(x, str) and SHA.fullmatch(x)):
        sys.exit(f"refused sha {x!r}: not a commit sha")
    return x


def pr_number(x):
    """A PR number from podium.json as an int, else None."""
    if isinstance(x, int) and not isinstance(x, bool):
        return x if x > 0 else None
    return int(x) if isinstance(x, str) and re.fullmatch(r"[0-9]{1,9}", x) else None


def git(p, *args, check=True, cwd=None):
    r = subprocess.run(git_argv(*args), cwd=cwd or p.repo, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def git_in(cwd, *args, timeout=60):
    """A git command in cwd that never prompts: (ok, stdout, the last line of stderr)."""
    try:
        r = subprocess.run(git_argv("-C", cwd, *args), capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, "", str(e)
    return r.returncode == 0, r.stdout.strip(), (r.stderr.strip().splitlines() or [""])[-1]


def sha_of(cwd, ref):
    ok, out, _ = git_in(cwd, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
    return out if ok and out else None


def checked_out(cwd, branch):
    """The worktree that has `branch` checked out, or None."""
    _, out, _ = git_in(cwd, "worktree", "list", "--porcelain")
    path = None
    for line in out.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
        elif line == f"branch refs/heads/{branch}":
            return path
    return None


def milestone_repo(p, m):
    """The milestone's branch in the run's repo as {branch, base, path, pr}: base is its `base`, else origin's default branch."""
    base = m.get("base") or git_in(p.repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")[1].split("/", 1)[-1] or None
    return {"branch": m.get("branch"), "base": base, "path": p.repo, "pr": m.get("pr")}


def story_commits(s):
    """(repo, commit) pairs: `commits` is {repo: [...]}, or a flat list (repo None) in single-repo runs."""
    c = s.get("commits") or []
    if isinstance(c, dict):
        return [(repo, x) for repo, xs in c.items() for x in xs]
    return [(None, x) for x in c]


# --- commits and merges ---------------------------------------------------------
def git_commits(p, rng, stats=True):
    rng = [rng] if isinstance(rng, str) else rng
    fmt = "--format=\x1e%H\x1f%s\x1f%ct"
    out = git(p, "log", "--reverse", "--no-merges", fmt, *(["--shortstat"] if stats else []), *rng).stdout
    commits = []
    for block in out.split("\x1e")[1:]:
        head, _, tail = block.partition("\n")
        sha, subject, at = head.split("\x1f")
        c = {"sha": sha[:10], "subject": subject, "at": UTC(at)}
        if stats:
            words = tail.replace(",", "").split()
            c["plus"] = next((int(words[i - 1]) for i, w in enumerate(words) if w.startswith("insertion")), 0)
            c["minus"] = next((int(words[i - 1]) for i, w in enumerate(words) if w.startswith("deletion")), 0)
        commits.append(c)
    return commits


def cmd_commits(p, args):
    """Each non-merge commit the git log args select, oldest first, as {sha, subject, plus, minus, at}.

    commits <git log args> [--into <target>] [--no-stats]
    The args are a range, or --no-walk <sha>.... --into writes them to that target's `commits` and prints a
    one-line summary instead. --no-stats leaves out plus and minus.
    """
    into = args[args.index("--into") + 1] if "--into" in args else None
    rng = [a for a in args if a not in ("--into", into, "--no-stats")]
    commits = git_commits(p, rng, "--no-stats" not in args)
    if into:
        obj, _, _ = p.resolve(into)
        obj["commits"] = [{k: v for k, v in c.items() if k != "at"} for c in commits]
        p.save()
        print(f"{len(commits)} commits into {into}")
    else:
        for c in commits:
            print(json.dumps(c, ensure_ascii=False))


def approvals_path():
    """approved.json beside human.json, outside every run dir, so a pull can't write it."""
    return os.path.join(os.path.dirname(human.HUMAN_FILE), "approved.json")


def approvals():
    """{sha256 of a command: the command} for each contract command this machine approved."""
    try:
        with open(approvals_path()) as f:
            got = json.load(f)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def digest(cmd):
    return hashlib.sha256(str(cmd).encode()).hexdigest()


def approved(p, cmd):
    """Whether this machine may run `cmd`, a command from podium.json: any in a run that doesn't sync, else only one
    whose exact text `podium approve all` recorded, since a pull may have written it."""
    return not p.synced() or digest(cmd) in approvals()


def contract_repo(p, c):
    return c.get("repo") or os.path.basename(p.repo)


def contract_line(p, c):
    """`<short digest> <repo>: <cmd>`, the digest's first 12 hex chars being what `approve <digest>` takes and the
    command quoted with every control character and non-ASCII character escaped, so nothing in it can disguise what
    runs."""
    return f"{digest(c['cmd'])[:12]} {contract_repo(p, c)}: {ascii(str(c['cmd']))}"


def require_approved(p, contract):
    """Print `CONTRACT-CHANGED <short digest> <repo>: <cmd>` for each command of `contract` this machine hasn't
    approved and exit 1 when there is one."""
    changed = [c for c in contract if not approved(p, c["cmd"])]
    for c in changed:
        print(f"CONTRACT-CHANGED {contract_line(p, c)}")
    if changed:
        sys.exit(1)


def dispatchers_path():
    """dispatcher.json beside human.json, outside every run dir, so a pull can't switch how stories run."""
    return os.path.join(os.path.dirname(human.HUMAN_FILE), "dispatcher.json")


def dispatchers():
    """{realpath of a run dir: `paseo` or `agent`}, how this machine dispatches each run's stories."""
    try:
        with open(dispatchers_path()) as f:
            got = json.load(f)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def set_dispatcher(p, choice):
    os.makedirs(os.path.dirname(dispatchers_path()), exist_ok=True)
    write_atomic(dispatchers_path(), json.dumps({**dispatchers(), os.path.realpath(p.root): choice}, indent=1))


def dispatcher(p):
    """This machine's dispatcher for the run, never podium.json's `dispatcher`, which a pull may have written. A run
    this machine never synced moves that key here once; a synced run without a choice gets `agent`, saying so once."""
    choice = dispatchers().get(os.path.realpath(p.root))
    if choice in DISPATCHERS:
        return choice
    if "sync" not in p.data:
        choice = p.data.get("dispatcher")
        if choice not in DISPATCHERS:
            return "agent"
    else:
        choice = "agent"
        print("DISPATCHER agent (podium dispatcher paseo to use Paseo)")
    set_dispatcher(p, choice)
    return choice


def cmd_dispatcher(p, args):
    """paseo | agent: how `launch` dispatches this run's stories on this machine, kept in dispatcher.json beside
    human.json, outside the run, so a pull can't change it. Prints `DISPATCHER <paseo|agent>`."""
    if len(args) != 1 or args[0] not in DISPATCHERS:
        sys.exit("dispatcher paseo | agent")
    set_dispatcher(p, args[0])
    print(f"DISPATCHER {args[0]}")


def chosen(pending, prefixes):
    """The digests of `pending` the prefixes name, each at least 8 hex chars matching exactly one; exits 1 otherwise."""
    picked = []
    for prefix in prefixes:
        if len(prefix) < 8 or not re.fullmatch(r"[0-9a-f]+", prefix):
            sys.exit(f"not a digest: {prefix} (8 or more hex chars)")
        hits = [k for k in pending if k.startswith(prefix)]
        if not hits:
            sys.exit(f"unknown digest {prefix}: no pending command has it")
        if len(hits) > 1:
            sys.exit(f"ambiguous digest {prefix}: {len(hits)} pending commands have it")
        picked.append(hits[0])
    return picked


def cmd_approve(p, args):
    """[all | <digest>...]: list the run's contract commands this machine hasn't approved, or approve some or all.

    A run that syncs runs a contract command only once this machine approved its exact text, kept as its sha256 in
    approved.json beside human.json; `merge` prints CONTRACT-CHANGED for any other. A digest is a prefix of 8 or
    more hex chars naming one pending command; an unknown or ambiguous one approves nothing and exits 1. Prints one of:
      PENDING <short digest> <repo>: <cmd>   one per command not approved
      APPROVED <n>                           n commands approved
    """
    if "all" in args and args != ["all"]:
        sys.exit("approve [all | <digest>...]")
    pending = {}
    for m in p.milestones():
        for c in (m.get("quality") or {}).get("contract") or []:
            if c.get("cmd") and not approved(p, c["cmd"]):
                pending.setdefault(digest(c["cmd"]), c)
    if not args:
        for c in pending.values():
            print(f"PENDING {contract_line(p, c)}")
        return
    picked = set(pending if args == ["all"] else chosen(pending, args))
    if picked:
        os.makedirs(os.path.dirname(approvals_path()), exist_ok=True)
        got = {**approvals(), **{k: pending[k]["cmd"] for k in picked}}
        write_atomic(approvals_path(), json.dumps(got, indent=1))
    print(f"APPROVED {len(picked)}")


MERGE_RESULTS = {1: "CONTRACT-CHANGED", 2: "CONFLICT", 3: "RED"}
LAND_RESULTS = {1: "NOT-MERGED"}


def outcome(step, results):
    """(exit code, result) of a step that exits on failure, `results` naming its exit codes: (None, None) when it
    returns."""
    try:
        step()
    except SystemExit as e:
        if e.code in (None, 0):
            return None, None
        if isinstance(e.code, int):
            return e.code, results.get(e.code, f"EXIT {e.code}")
        return 1, f"ERROR: {e.code}"
    return None, None


def cmd_merge(p, args):
    """Merge story/<id> into its milestone's branch (--no-ff), then run the milestone's contract there.

    merge <story>... | <milestone>/<story>... [--land [--next]] [--force]
    It merges in the worktree that has the milestone's branch checked out, else in the repo checkout, and runs
    quality.contract[].cmd there to <run dir>/contract.log. The merge that completes a wave (no story of the
    milestone left working or in approval) carries `wave: true` on its `merged` event. Prints one of:
      MERGED <id> <n> commits; ready: <ids>   story done, commits recorded
      CONFLICT <id> <n>                        merge aborted; n = conflicts so far
      RED <id> <cmd> + the log's last 40 lines merge undone (reset --hard ORIG_HEAD)
      CONTRACT-CHANGED <digest> <repo>: <cmd>  not approved on this machine (`approve`); nothing merged
    Several ids, or --land, are a queue merged in order, each printing its line; --land runs `land` (--next passed on)
    on each MERGED before the next id. The first result other than MERGED stops the queue, which exits as that step did:
      STOPPED <id> <CONFLICT|RED|CONTRACT-CHANGED|NOT-MERGED|ERROR: <why>>
      PENDING <ids> | PENDING -                   the ids it never reached
    A milestone another person owns is refused unless --force.
    """
    ids = [a for a in args if a not in ("--force", "--land", "--next")]
    if not ids or "--next" in args and "--land" not in args:
        sys.exit("merge <story>... | <milestone>/<story>... [--land [--next]] [--force]")
    if len(ids) == 1 and "--land" not in args:
        return merge_story(p, ids[0], "--force" in args)
    seen, queue = set(), []
    for ident in ids:
        m, s = find_story(p, ident)
        key = (m["id"], s["id"]) if s else ident
        if key not in seen:
            seen.add(key)
            queue.append(ident)
    land_args = [a for a in ("--next", "--force") if a in args]
    for i, ident in enumerate(queue):
        code, result = outcome(lambda: merge_story(p, ident, "--force" in args), MERGE_RESULTS)
        if code is None and "--land" in args:
            code, result = outcome(lambda: cmd_land(p, [ident, *land_args]), LAND_RESULTS)
        if code is not None:
            print(f"STOPPED {ident} {result}")
            print(f"PENDING {' '.join(queue[i + 1:]) or '-'}")
            sys.exit(code)


def merge_story(p, target, force):
    """`merge` of one story, exiting with its result's code: 1 CONTRACT-CHANGED, 2 CONFLICT, 3 RED."""
    mid, _, sid = target.rpartition("/")
    require_owner(p, p.story(sid, mid or None)[0]["id"], force)
    m, s = p.story(sid, mid or None)  # claiming pulls, which replaces p.data
    branch, story_branch = m.get("branch"), f"story/{safe_id(s['id'])}"
    if not branch:
        sys.exit(f"{m['id']} has no branch")
    branch_name(branch)
    require_approved(p, m.get("quality", {}).get("contract", []))
    tree = checked_out(p.repo, branch)
    cwd = tree if tree and os.path.isdir(tree) else p.repo
    if git(p, "rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip() != branch:
        git(p, "switch", "--end-of-options", branch, cwd=cwd)
    commits = git_commits(p, ["--end-of-options", f"{branch}..{story_branch}"])
    if git(p, "merge", "--no-ff", "--no-edit", story_branch, check=False, cwd=cwd).returncode:
        git(p, "merge", "--abort", check=False, cwd=cwd)
        s["conflicts"] = s.get("conflicts", 0) + 1
        p.event("conflict", m["id"], s["id"])
        p.save()
        print(f"CONFLICT {s['id']} {s['conflicts']}")
        sys.exit(2)
    log = os.path.join(p.root, "contract.log")
    results = []
    open(log, "w").close()
    for c in m.get("quality", {}).get("contract", []):
        with open(log, "a") as f:
            f.write(f"$ {c['cmd']}\n")
            f.flush()
            ok = subprocess.run(c["cmd"], shell=True, cwd=cwd, stdout=f, stderr=subprocess.STDOUT).returncode == 0
        results.append({"cmd": c["cmd"], "ok": ok, "at": NOW(), "story": s["id"]})
        if not ok:
            git(p, "reset", "--hard", "ORIG_HEAD", cwd=cwd)
            m["quality"]["contract"] = results + m["quality"]["contract"][len(results):]
            p.save()
            with open(log) as f:
                tail = f.read().splitlines()[-40:]
            print(f"RED {s['id']} {c['cmd']}\n" + "\n".join(tail))
            sys.exit(3)
    m.setdefault("quality", {})["contract"] = results
    s.update(status="done", commits=[{k: v for k, v in c.items() if k != "at"} for c in commits], finishedAt=NOW())
    for c in commits:
        p.event("commit", m["id"], s["id"], at=c["at"], sha=c["sha"], subject=c["subject"])
    p.save()
    m = p.milestone(m["id"])  # as saved, with what other commands wrote while the contract ran
    wave = not any(o.get("status") in ("working", "approval") for o in m.get("stories", []))
    p.event("merged", m["id"], s["id"], into=branch, **({"wave": True} if wave else {}))
    print(f"MERGED {s['id']} {len(commits)} commits; ready: {' '.join(p.ready(m)) or '-'}")


def cmd_backfill(p, _):
    """Rebuild the planned, commit and landed lines of events.jsonl from the milestones' commits, brief dates and
    landedSha, keep every other line, and sort by time."""
    events_path = os.path.join(p.dir, "events.jsonl")
    shas = {commit_sha(c["sha"]) for m in p.milestones() for s in m.get("stories", []) for c in s.get("commits", [])}
    shas |= {commit_sha(m["landedSha"]) for m in p.milestones() if m.get("landedSha")}
    when = {}
    if shas:
        for line in git(p, "log", "--no-walk=unsorted", "--format=%H %ct", "--end-of-options", *shas).stdout.splitlines():
            full, at = line.split()
            for sha in shas:
                if full.startswith(sha):
                    when[sha] = UTC(at)
    new = []
    for m in p.milestones():
        commits = [(c, s["id"]) for s in m.get("stories", []) for c in s.get("commits", [])]
        if not commits:
            continue
        times = [when[c["sha"]] for c, _ in commits if c["sha"] in when]
        brief = m.get("brief")
        if brief:
            added = git(p, "log", "--diff-filter=A", "--format=%ct", "--", os.path.join(p.root, brief), check=False)
            times += [UTC(t) for t in added.stdout.split()[-1:]]
        if times:
            new.append({"at": min(times), "type": "planned", "milestone": m["id"]})
        seen = set()
        for c, sid in commits:
            if c["sha"] in seen or c["sha"] == m.get("landedSha") or c["sha"] not in when:
                continue
            seen.add(c["sha"])
            new.append({"at": when[c["sha"]], "type": "commit", "milestone": m["id"], "story": sid,
                        "sha": c["sha"], "subject": c["subject"]})
        if m.get("landedSha") in when:
            subject = git(p, "show", "-s", "--format=%s", "--end-of-options", m["landedSha"]).stdout.strip()
            new.append({"at": when[m["landedSha"]], "type": "landed", "milestone": m["id"],
                        "sha": m["landedSha"], "subject": subject})
    with p.locked():  # the lines as they are now, so an event appended while git ran stays
        kept = []
        if os.path.exists(events_path):
            with open(events_path) as f:
                kept = [e for e in (json.loads(l) for l in f if l.strip()) if e.get("type") not in GENERATED]
        rows = sorted(kept + new, key=lambda e: e.get("at", ""))
        with open(events_path + ".tmp", "w") as f:
            f.writelines(json.dumps(e, ensure_ascii=False) + "\n" for e in rows)
        os.replace(events_path + ".tmp", events_path)
    missing = len(shas) - len(when)
    print(f"{len(new)} generated + {len(kept)} kept = {len(rows)} events" + (f"; {missing} shas not in git" if missing else ""))


# --- pull requests ----------------------------------------------------------------
def gh_pr(p, number):
    """gh's view of one PR: {state, isDraft, url, mergeCommit, mergedAt}, or (None, why it failed)."""
    n = pr_number(number)
    if n is None:
        return None, f"not a PR number: {number!r}"
    out = subprocess.run(["gh", "pr", "view", str(n), "--json", "state,isDraft,url,mergeCommit,mergedAt"],
                         cwd=p.repo, capture_output=True, text=True)
    if out.returncode:
        return None, (out.stderr.strip().splitlines() or ["gh failed"])[-1]
    return json.loads(out.stdout), None


def refresh_pr(p, m, pr):
    """Re-read the milestone's PR and write a changed state back with a `pr` event: (state, old state, gh's answer, error)."""
    got, why = gh_pr(p, pr["number"])
    if not got:
        return None, pr.get("state"), None, why
    state = "draft" if got.get("isDraft") and got["state"] == "OPEN" else got["state"].lower()
    old = pr.get("state")
    pr.update(state=state, url=got.get("url") or pr.get("url"))
    if state != old:
        p.event("pr", m["id"], number=pr["number"], state=state, was=old, url=pr["url"])
    return state, old, got, None


def cmd_prs(p, args):
    """Refresh the state of a milestone's `pr` with `gh pr view`, every milestone's when none is named.

    prs [<milestone>]
    Merged PRs are final and skipped. One line per PR: `<milestone> #<n> <state> [(was <old>)]`, or
    `error: <message>`. A changed state is written back with a `pr` event. Exits 1 on any error.
    """
    errors = changed = 0
    for m in [p.milestone(args[0])] if args else p.milestones():
        pr = m.get("pr")
        if not pr or pr.get("state") == "merged":
            continue
        state, old, _, why = refresh_pr(p, m, pr)
        if why:
            errors += 1
            print(f"{m['id']} #{pr['number']} error: {why}")
            continue
        changed += state != old
        print(f"{m['id']} #{pr['number']} {state}" + (f" (was {old})" if state != old else ""))
    if changed:
        p.save()
    if errors:
        sys.exit(1)


# --- a story agent's start: its brief and the planning sections it names --------
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def norm(text):
    """Lowercase words only: how headings, anchors and quoted spans compare."""
    return " ".join(re.sub(r"[^\w]+", " ", urllib.parse.unquote(text).lower()).split())


def slug(text):
    """A heading's GitHub-style anchor."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def md_sections(path):
    """(lines, [(level, heading, first line, end line)]) of a markdown file; a section runs to the next heading
    of the same or a higher level, and headings inside code fences don't count."""
    with open(path) as f:
        lines = f.read().splitlines()
    heads, fence = [], None
    for i, line in enumerate(lines):
        mark = line.lstrip()[:3]
        if mark in ("```", "~~~"):
            fence = None if fence == mark else fence or mark
        elif not fence and (h := HEADING.match(line)):
            heads.append((len(h[1]), h[2].strip(), i))
    return lines, [(lvl, text, i, next((k for l2, _, k in heads[j + 1:] if l2 <= lvl), len(lines)))
                   for j, (lvl, text, i) in enumerate(heads)]


def planning_files(p, m):
    """The milestone's planning files that exist: its .md `artifacts`, its `spec` (a folder means its spec.md,
    plan.md and tasks.md), architecture*.md and spec/{spec,tasks}.md, each relative to the run dir or its repo."""
    names = [a["path"] for a in m.get("artifacts") or [] if str(a.get("path", "")).endswith(".md")]
    spec = m.get("spec")
    if spec:
        names += [os.path.join(spec, n) for n in ("spec.md", "plan.md", "tasks.md")] if not spec.endswith(".md") else [spec]
    names += ["spec/spec.md", "spec/tasks.md"] + sorted(os.path.relpath(f, p.root) for f in glob.glob(os.path.join(p.root, "architecture*.md")))
    out = {}
    for n in names:
        for base in (p.root, p.repo):
            full = os.path.realpath(os.path.join(base, os.path.expanduser(n)))
            if os.path.isfile(full):
                out.setdefault(full, None)
                break
    return list(out)


def brief_refs(text):
    """(file or None, heading or anchor) for each `file.md#heading`, `[..](file.md#anchor)` and `[file.md ]§ Heading` in a brief."""
    refs = re.findall(r"\]\(([^)\s]+?\.md)#([^)]+)\)", text)
    refs += re.findall(r"`([^`\s]+?\.md)#([^`]+)`", text)
    refs += re.findall(r"(?<![\w(`/.-])([\w./-]+\.md)#([^\s,;)`]+(?: [^\s,;)`#§]+)*)", text)
    refs += [(f or None, h.strip()) for f, h in re.findall(r"(?:([\w./-]+\.md)\s*)?§\s*([^`)\n,;§]+)", text)]
    return list(dict.fromkeys(refs))


def find_file(p, name, brief_dir, files):
    """A referenced planning file: by path from the brief, the run dir or its repo, else by name among the planning files."""
    for base in (brief_dir, p.root, p.repo):
        full = os.path.realpath(os.path.join(base, name))
        if os.path.isfile(full):
            return full
    return next((f for f in files if f.endswith(os.sep + name) or os.path.basename(f) == os.path.basename(name)), None)


def cmd_brief(p, args):
    """A story agent's whole starting context: its brief, then each planning section the brief references.

    brief [<milestone>/]<story> [--milestone M]
    The planning files are the milestone's .md `artifacts`, its `spec`, architecture*.md, spec/spec.md and
    spec/tasks.md. A reference is `file.md#heading` or `[..](file.md#anchor)`, `[file.md ]§ Heading`, a
    heading's text in backticks or quotes, and the story's own `## <id>` section of tasks.md. Each section
    prints under `=== <file> § <heading>`; a reference that matches nothing prints `MISSING <ref>`.
    """
    named = args[args.index("--milestone") + 1] if "--milestone" in args else None
    target = next((a for a in args if a not in ("--milestone", named)), None)
    if not target:
        sys.exit("brief [<milestone>/]<story> [--milestone M]")
    mid, _, sid = target.rpartition("/")
    m, s = p.story(sid, mid or named)
    path = os.path.join(p.root, s["brief"]) if s.get("brief") else os.path.join(p.dir, "stories", safe_id(m["id"]), f"{safe_id(sid)}.md")
    if not os.path.isfile(path):
        sys.exit(f"no brief at {path}")
    with open(path) as f:
        brief = f.read()
    picked, missing = brief_sections(p, m, sid, brief, os.path.dirname(path))
    print(brief.rstrip())
    for f, hits in picked.items():
        if not hits:
            continue
        lines = md_sections(f)[0]
        base = next((b for b in map(os.path.realpath, (p.root, p.repo)) if f.startswith(b + os.sep)), None)
        rel = os.path.relpath(f, base) if base else f
        spans = sorted(hits, key=lambda h: (h[0], -h[1]))
        kept = [h for h in spans if not any(o[0] <= h[0] and h[1] <= o[1] and o != h for o in spans)]
        for first, end, heading in kept:
            print(f"\n=== {rel} § {heading}")
            print("\n".join(lines[first:end]).rstrip())
    for ref in missing:
        print(f"MISSING {ref}")


def brief_sections(p, m, sid, brief, brief_dir):
    """({file: {(first line, end line, heading)}}, [each reference that matches nothing]) for story `sid`'s brief text,
    as cmd_brief prints them."""
    files = planning_files(p, m)
    picked, missing = {}, []

    def pick(f, test):
        lines, secs = md_sections(f)
        hits = [(i, end, h) for lvl, h, i, end in secs if test(lvl, h)]
        picked.setdefault(f, set()).update(hits)
        return bool(hits)

    for name, ref in brief_refs(brief):
        f = find_file(p, name, brief_dir, files) if name else None
        words = ref.split(" ")
        for n in range(len(words), 0, -1):  # a bare reference runs on into prose: drop words until a heading fits
            want = lambda lvl, h, r=" ".join(words[:n]): norm(h) == norm(r) or slug(h) == r.strip().lower()
            if pick(f, want) if f else any([pick(g, want) for g in files]):
                break
        else:
            missing.append(f"{name}#{ref}" if name else f"§ {ref}")
    quoted = {norm(a or b) for a, b in re.findall(r"`([^`\n]+)`|\"([^\"\n]+)\"", brief)}
    own = re.compile(rf"(?:Story\s+)?{re.escape(sid)}(?![\w])", re.I)
    for f in files:
        pick(f, lambda lvl, h: lvl > 1 and norm(h) in quoted)
        if os.path.basename(f) == "tasks.md":
            pick(f, lambda lvl, h: own.match(h.strip("`*_ ")))
    return picked, missing


# --- breakdown: a milestone's tasks.md into its stories and their briefs ----------
USER_STORY = re.compile(r"^Phase\s+\d+\s*[:.—–-]\s*User Story\s+(\d+)(?!\d)\s*[:.—–-]?\s*(.*)$", re.I)
FIELD = re.compile(r"\*\*([A-Z][\w ]*?)(?::\*\*|\*\*:)")
TASK = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+(T\d+)(?!\w)\s*(.*)$")
STORY_REF = re.compile(r"\b(?:US|[Uu]ser [Ss]tory\s+|[Ss]tory\s+)(\d+)(?:[–-](?:US)?(\d+)|\s*[–-]\s*US(\d+))?(?!\w)")
DEPENDS = re.compile(r"\b(?:depends? on|needs|requires|after|blocked by)\b", re.I)
CLAUSE_END = re.compile(r"\s[—–-]{1,2}\s|──|[;.](?:\s|$)|\bbut\b")
PATHS = re.compile(r"`([^`\s]+)`|(?<![\w/.:`-])((?:[\w.@\[\]-]+/)+[\w.@\[\]-]*\.[A-Za-z]\w{0,5})(?![\w/])")
CRITICAL = re.compile(r"\b(?:money|payments?|prices?|currenc(?:y|ies)|dates?|time ?zones?|concurren\w*|auth|authentication|"
                      r"authori[sz]ation|oauth|migrations?|algorithms?)\b", re.I)


def story_refs(text):
    """The user-story numbers `text` names (`US2`, `User Story 2`, `US1–US3`), ranges spelled out."""
    out = []
    for a, b, c in STORY_REF.findall(text or ""):
        out += range(int(a), int(b or c or a) + 1)
    return list(dict.fromkeys(out))


def story_deps(lines):
    """{user-story number: [the numbers it depends on]} from a Dependencies section, sentence by sentence: the stories
    a sentence names before its first `depends on`, `needs`, `requires`, `after` or `blocked by` depend on those each of
    them names up to the end of its clause, unless negated, so `US5 ── needs US4` is a dependency, and neither
    `US2: after Foundational - may integrate with US1` nor `US4 needs nothing from US1–US3` is one."""
    deps = {}
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        for sentence in re.split(r";\s*|\.\s+", line):
            cues = list(DEPENDS.finditer(sentence))
            needed = [n for c in cues if not re.search(r"(?:\bnot|n't|\bnever)\s+$", sentence[:c.start()])
                      and not re.match(r"\s*(?:nothing|none|no|not)\b", sentence[c.end():])
                      for n in story_refs(CLAUSE_END.split(sentence[c.end():])[0])]
            for k in story_refs(sentence[:cues[0].start()] if cues else sentence):
                deps[k] = list(dict.fromkeys(deps.get(k, []) + [n for n in needed if n != k]))
    return deps


def yes_no(text):
    word = (text or "").strip().lower()
    return True if word.startswith("yes") else False if word.startswith("no") else None


def listed(text):
    """The items of a field, one per comma or line, commas inside backticks kept."""
    items = (x.strip().rstrip(".").strip() for x in re.findall(r"(?:`[^`]*`|[^,`\n])+", text or ""))
    return [x for x in items if x and x.lower() not in ("and", "none")]


def task_paths(text):
    """The file paths a task line names: in backticks with a `/` or an extension, or bare with both."""
    out = []
    for ticked, bare in PATHS.findall(text):
        if ticked and "://" not in ticked and ("/" in ticked or re.search(r"\w\.[A-Za-z]\w{1,5}$", ticked)):
            out.append(ticked)
        elif bare:
            out.append(bare)
    return [re.sub(r"^\.?/", "", f.rstrip("/")) for f in out]


def parse_tasks(path):
    """deep-plan's speckit tasks.md: {"groups": [...], "spec": the spec.md beside it or None}.

    A group is a `## Phase <n>: User Story <k> - <title> (Priority: P<n>)` section: its `**Goal**:`, `**Critical**:`
    and `**Context**:` fields, its task lines (`- [ ] T012 [P] [US1] … in path/to/file`, continuation lines joined),
    the files they name, the spec.md heading of its user story, and its deps from the file's Dependencies section
    (story_deps). A story with no `**Critical**:` field is critical when its title, goal or tasks name money, dates,
    time zones, concurrency, auth, migrations or algorithms. A field neither gives is None.
    """
    lines, secs = md_sections(path)
    said = [line for _, h, i, end in secs if norm(h).startswith("dependencies") for line in lines[i + 1:end]]
    deps = story_deps(said) if any(norm(h).startswith("dependencies") for _, h, _, _ in secs) else None
    spec = os.path.join(os.path.dirname(path), "spec.md")
    spec_heads = [h for _, h, _, _ in md_sections(spec)[1]] if os.path.isfile(spec) else []
    groups = []
    for lvl, heading, i, end in secs:
        hit = USER_STORY.match(heading.strip("`*_ "))
        if lvl != 2 or not hit:
            continue
        k, body = int(hit[1]), lines[i + 1:end]
        title = re.sub(r"\s*\((?:Priority:\s*)?P\d+\).*$|\s*🎯.*$", "", hit[2]).strip() or f"User Story {k}"
        tasks, joining = [], False
        for line in body:
            task = TASK.match(line)
            if task:
                tasks.append([task[1], task[2].strip()])
            elif joining and line[:1].isspace() and line.strip() and not re.match(r"\s*(?:[-*]|\d+[.)])\s", line):
                tasks[-1][1] += " " + line.strip()
                continue
            joining = bool(task)
        head = "\n".join(body[:next((n for n, line in enumerate(body) if TASK.match(line) or line.startswith("#")), len(body))])
        marks = list(FIELD.finditer(head))
        fields = {mk[1].strip().lower(): head[mk.end():marks[n + 1].start() if n + 1 < len(marks) else len(head)].strip()
                  for n, mk in enumerate(marks)}
        goal = " ".join(fields.get("goal", "").split()) or None
        critical = yes_no(fields.get("critical"))
        if critical is None and CRITICAL.search(" ".join([title, goal or ""] + [t for _, t in tasks])):
            critical = True
        groups.append({"k": k, "heading": heading.strip(), "title": title, "story": goal,
                       "deps": None if deps is None else deps.get(k), "critical": critical,
                       "context": listed(fields.get("context")),
                       "spec": next((h for h in spec_heads if re.match(rf"user story {k}\b", norm(h))), None),
                       "files": list(dict.fromkeys(f for _, t in tasks for f in task_paths(t))),
                       "tasks": [(tid, re.sub(r"\[(?:P|US\d+)\]\s*", "", text).strip()) for tid, text in tasks]})
    return {"groups": groups, "spec": spec if spec_heads else None}


def waves(ids, after):
    """(waves, the ids left on a cycle): each wave the ids whose `after` ids are all in earlier waves."""
    done, out, left = set(), [], list(ids)
    while left:
        wave = [x for x in left if set(after.get(x, ())) & set(ids) <= done]
        if not wave:
            break
        out.append(wave)
        done.update(wave)
        left = [x for x in left if x not in done]
    return out, left


def reaches(a, b, deps):
    """Whether story a depends on b, directly or through others; reaches(a, a, deps) when a is on a loop."""
    seen, todo = set(), [a]
    while todo:
        x = todo.pop()
        for d in deps.get(x, ()):
            if d == b:
                return True
            if d not in seen:
                seen.add(d)
                todo.append(d)
    return False


def sharing_order(chain, deps):
    """The stories that share a file in id order, except that each comes after every one of them it depends on."""
    out, left = [], list(chain)
    while left:
        x = next((x for x in left if not any(reaches(x, y, deps) for y in left if y != x)), left[0])
        out.append(x)
        left.remove(x)
    return out


def run_path(p, path):
    """`path` as the run's files name it: from the run dir when inside it, else from the repo."""
    full = os.path.realpath(path)
    base = next((b for b in map(os.path.realpath, (p.root, p.repo)) if full.startswith(b + os.sep)), None)
    return os.path.relpath(full, base) if base else full


def heading_ref(path, heading):
    return f"`{path}#{slug(heading) if '`' in heading else heading}`"


def brief_text(m, s, g, context):
    """phase-2-breakdown.md's brief for one story, from its tasks.md section."""
    contract = [c["cmd"] for c in (m.get("quality") or {}).get("contract") or [] if isinstance(c, dict) and c.get("cmd")]
    out = [f"# {s['id']} · {s['title']}", "", "## Goal", g["story"] or s["title"], "", "## Acceptance"]
    out += [f"- [ ] {tid} {text}" for tid, text in g["tasks"]] + ["", "## Files in scope"] + [f"- {f}" for f in s["files"]]
    out += ["", "## Context"] + [f"- {c}" for c in context] + ["", "## Contract"]
    out += [f"- `{c}`" for c in contract] or ["- the `gates.sh` call (deep-plan's SKILL.md, Shared rules, Contract runs)"]
    out += ["", "## Done when", f"One commit on story/{s['id']} with trailer `Story: {s['id']}`, the contract green, "
            "`COMMITTED <sha>` logged."]
    return "\n".join(out) + "\n"


def started(s):
    """Whether a story has been dispatched at least once: a rerun of breakdown leaves it alone."""
    return (s.get("status") or "todo") not in ("todo", "blocked") or bool(s.get("startedAt") or s.get("attempts"))


def cmd_breakdown(p, args):
    """<tasks.md> [--milestone M] [--prefix P] [--dry-run] [--force]: the milestone's stories and briefs from deep-plan's
    speckit tasks.md (phase-2-breakdown.md).

    One story per `## Phase <n>: User Story <k>` section, id `S<k>`, or `<P><k>` with --prefix: title, summary, files
    from its task lines, deps from the Dependencies section, overlapAfter, critical and its model, and its brief at
    podium/stories/<M>/<id>.md. A rerun updates each story in place; a story already started stays as it is.
      STORY <id> <repo> deps=<ids|-> files=<n> missing=<fields|->
      MISSING <id> <field> | MISSING <id> dep <id> | MISSING <id> ref <reference brief can't find>
      OVERLAP <earlier> <later> <file>      the later one waits for the earlier: a shared file, no dependency path
      KEPT <id> started                     left as it is
      WAVES <ids> | <ids> …                 from deps and overlapAfter
      CYCLE <ids>                           the stories on a loop of dependencies: nothing written, exit 1
    --dry-run prints the same and writes nothing.
    """
    usage = "breakdown <tasks.md> [--milestone M] [--prefix P] [--dry-run] [--force]"
    values, rest = split_flags(args, ("--milestone", "--prefix"), usage)
    named, prefix = values.get("--milestone"), values.get("--prefix", "S")
    switches = [a for a in rest if a in ("--dry-run", "--force")]
    rest = [a for a in rest if a not in switches]
    if len(rest) != 1 or not re.fullmatch(r"[A-Za-z]{1,8}", prefix):
        sys.exit(usage)
    path, dry = os.path.abspath(rest[0]), "--dry-run" in switches
    if not os.path.isfile(path):
        sys.exit(f"no tasks file at {path}")
    m = p.milestone(named)
    mid = safe_id(m["id"])
    if not dry:
        require_owner(p, mid, "--force" in switches)
        m = p.milestone(mid)
    parsed = parse_tasks(path)
    groups = parsed["groups"]
    if not groups:
        sys.exit(f"no `## Phase <n>: User Story <k>` section in {path}")
    ks = [g["k"] for g in groups]
    twice = sorted({k for k in ks if ks.count(k) > 1})
    if twice:
        sys.exit(f"{path}: User Story {' '.join(map(str, twice))} more than once")
    ident = {k: safe_id(f"{prefix}{k}") for k in ks}
    ids = list(ident.values())
    deps = {ident[g["k"]]: [ident[d] for d in g["deps"] or [] if d in ident] for g in groups}
    files = {ident[g["k"]]: g["files"] for g in groups}
    after, lines = {x: [] for x in ids}, []
    for f in dict.fromkeys(f for x in ids for f in files[x]):
        chain = sharing_order([x for x in ids if f in files[x]], deps)
        for a, b in zip(chain, chain[1:]):
            if not reaches(a, b, deps) and not reaches(b, a, deps):
                after[b] = list(dict.fromkeys(after[b] + [a]))
                lines.append(f"OVERLAP {a} {b} {f}")
    rel, repo = run_path(p, path), os.path.basename(p.repo)
    existing = {s.get("id"): s for s in m.get("stories") or []}
    stories, briefs, kept = [], {}, []
    for g in groups:
        sid = ident[g["k"]]
        context = g["context"] + ([heading_ref(run_path(p, parsed["spec"]), g["spec"])] if g["spec"] else [])
        missing = ([k for k in ("story", "deps", "critical") if g[k] is None]
                   + [k for k, v in (("context", context), ("files", g["files"]), ("tasks", g["tasks"])) if not v])
        s = {"id": sid, "title": g["title"], "summary": re.split(r"(?<=[.!?])\s", g["story"] or g["title"])[0][:200],
             "files": g["files"], "deps": deps[sid], "overlapAfter": after[sid],
             "critical": bool(g["critical"]), "model": "opus" if g["critical"] else "sonnet",
             "brief": os.path.relpath(os.path.join(p.dir, "stories", mid, f"{sid}.md"), p.root)}
        text = brief_text(m, s, g, context + [heading_ref(rel, g["heading"])])
        print(f"STORY {sid} {repo} deps={','.join(s['deps']) or '-'} files={len(s['files'])} missing={','.join(missing) or '-'}")
        for k in missing:
            print(f"MISSING {sid} {k}")
        for d in g["deps"] or []:
            if d not in ident:
                print(f"MISSING {sid} dep {prefix}{d}")
        for ref in brief_sections(p, m, sid, text, os.path.dirname(os.path.join(p.root, s["brief"])))[1]:
            print(f"MISSING {sid} ref {ref}")
        if sid in existing and started(existing[sid]):
            kept.append(f"KEPT {sid} started")
            continue
        stories.append(s)
        briefs[sid] = text
    for line in lines + kept:
        print(line)
    order = {x: deps[x] + after[x] for x in ids}
    built, stuck = waves(ids, order)
    print("WAVES " + (" | ".join(" ".join(w) for w in built) or "-"))
    if stuck:
        print(f"CYCLE {' '.join(x for x in stuck if reaches(x, x, order))}")
        sys.exit("breakdown: the dependencies loop, nothing written")
    if dry:
        return
    for sid, text in briefs.items():
        full = os.path.join(p.dir, "stories", mid, f"{sid}.md")
        os.makedirs(os.path.dirname(full), exist_ok=True)
        write_atomic(full, text)
    index = {s.get("id"): n for n, s in enumerate(m.get("stories") or [])}
    sets = []
    for s in stories:
        if s["id"] in index:
            sets += [f"stories.{index[s['id']]}.{k}={json.dumps(v)}" for k, v in s.items() if k != "id"]
        else:
            sets.append("stories+=" + json.dumps({**s, "status": "todo", "attempts": 0}))
    if sets:
        apply_set(p, [f"milestone:{mid}", *sets, "--event", "status", f"text=breakdown: {len(stories)} stories from {rel}"])
        p.save()


# --- dispatch: worktrees, the story prompt, Paseo ------------------------------
def paseo_bin():
    return os.environ.get("PODIUM_PASEO") or shutil.which("paseo") or os.path.expanduser("~/.local/bin/paseo")


def podium_cli(root):
    """How an agent runs `podium` on the run."""
    return f"podium --dir {shlex.quote(os.path.abspath(root))}"


def story_trees(p, m, s):
    """[(repo, its checkout, the story's worktree, the branch it starts from)]: one per repo in the story's `repos`
    under <run dir>/worktrees/<id>/, else one beside the run's repo."""
    sid = safe_id(s["id"])
    if s.get("repos"):
        repos = m.get("repos") or {}
        trees = [(r, checkout(p, (repos.get(r) or {}).get("path")),
                  os.path.join(p.root, "worktrees", sid, r), (repos.get(r) or {}).get("branch")) for r in map(repo_name, s["repos"])]
    else:
        repo = os.path.dirname(p.root)
        trees = [(os.path.basename(repo), repo, f"{repo}-{sid}", m.get("branch"))]
    for _, _, _, start in trees:
        if start:
            branch_name(start)
    return trees


def story_prompt(p, m, s, retry=None):
    """phase-3-build.md's story prompt (its single source), filled in for one story."""
    with open(PHASE_3) as f:
        template = re.search(r"Story prompt[^\n]*\n+```\n(.*?)\n```", f.read(), re.S).group(1)
    trees = "\n".join(f"{r}: {t}" for r, _, t, _ in story_trees(p, m, s))
    text = (template.replace(" <repo>: <path>, one per line.", "\n" + trees).replace("<podium>", podium_cli(p.root))
            .replace("<podium dir>", podium_dir(p.root)).replace("<milestone>", safe_id(m["id"])).replace("<id>", s["id"]))
    return text + (f"\n\nPrevious attempt failed: {retry}" if retry else "")


def handoff_prompt(p, m, s):
    """The story prompt for a session of the user's own, after a step that creates the worktrees `launch` otherwise
    makes: one per repo in the story's `repos`, else one beside the repo."""
    trees = story_trees(p, m, s)
    setup = [f"git -C {shlex.quote(str(src))} worktree add -b story/{s['id']} {shlex.quote(tree)} {shlex.quote(str(branch))}"
             for _, src, tree, branch in trees]
    return (f"You run outside the orchestrator, which tracks you only through the progress file named below: "
            f"log STARTED before anything else and end on COMMITTED or FAILED. It merges your commit when it reads COMMITTED.\n\n"
            f"First set up your worktree{'s' if len(trees) > 1 else ''}, then work only there:\n" + "\n".join(setup) + "\n\n"
            + story_prompt(p, m, s) + "\n")


def find_story(p, ident):
    """(milestone, story) for `<story>` of the active milestone or `<milestone>/<story>`, else (None, None)."""
    mid, _, sid = (ident or "").rpartition("/")
    mid = mid or p.active().get("milestone")
    m = next((x for x in p.milestones() if x.get("id") == mid), None)
    s = next((x for x in (m or {}).get("stories", []) if x.get("id") == sid), None)
    return (m, s) if s else (None, None)


def prompt(p, kind, target_id):
    """The Podium's prompt of `kind` for a milestone (`plan`) or a story (`assign`, `handoff`), or None."""
    if kind == "plan":
        return f"/orchestrate-deep-plans {target_id}"
    m, s = find_story(p, target_id)
    if not s:
        return None
    if kind == "assign":
        return story_prompt(p, m, s)
    if kind == "handoff":
        return handoff_prompt(p, m, s)
    return None


def paseo(*args):
    """The Paseo CLI's JSON answer, or (None, why it failed)."""
    try:
        r = subprocess.run([paseo_bin(), *args, "--json"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if r.returncode:
        return None, ((r.stderr or r.stdout).strip().splitlines() or ["paseo failed"])[-1]
    try:
        return json.JSONDecoder().raw_decode(r.stdout[min(i for i in (r.stdout.find("{"), r.stdout.find("[")) if i >= 0):])[0], None
    except ValueError:
        return None, f"paseo answered {r.stdout.strip()[:80]!r}"


def paseo_provider(model, _models={}):
    """`claude/<id>` for a story's model: an id as given, else the newest one Paseo lists for opus or sonnet."""
    if "/" in model:
        return model
    if model.startswith("claude-"):
        return f"claude/{model}"
    if "ids" not in _models:
        _models["ids"] = [x.get("id", "") for x in paseo("provider", "models", "claude")[0] or []]
    hit = next((i for i in _models["ids"] if i.startswith(f"claude-{model}-") and "[" not in i), None)
    return f"claude/{hit or model}"


def recorded_trees(p, m, s):
    """[(checkout, worktree)] of the story: each worktree where podium.json recorded it, else where launch puts it."""
    recorded = s.get("worktrees") or {}
    return [(src, checkout(p, recorded.get(name)) or tree) for name, src, tree, _ in story_trees(p, m, s)]


def retire(p, m, s):
    """Archive the story's Paseo workspace, which archives its agent too, and remove its worktrees; a line for each kept."""
    kept, a = [], s.get("agent") or {}
    if a.get("backend") == "paseo" and (a.get("workspace") or a.get("id")):
        target = a.get("workspace") or a["id"]
        if not (isinstance(target, str) and PASEO_ID.fullmatch(target)):
            why = "not a Paseo id"
        else:
            _, why = paseo("workspace", "archive", target) if a.get("workspace") else paseo("archive", "--force", target)
        if why:
            kept.append(f"KEPT {s['id']} paseo {target}: {why}")
    for src, tree in recorded_trees(p, m, s):
        if os.path.exists(tree):
            ok, _, why = git_in(src or tree, "worktree", "remove", tree)
            if not ok:
                kept.append(f"KEPT {tree}: {why}")
    return kept


def unblock(m):
    """Stories blocked by a failure no longer upstream of them go back to todo."""
    by_id = {s["id"]: s for s in m.get("stories", [])}

    def failed_upstream(sid, seen):
        for d in by_id.get(sid, {}).get("deps", []):
            if d not in seen and (by_id.get(d, {}).get("status") == "failed" or failed_upstream(d, seen | {d})):
                return True
        return False
    for s in by_id.values():
        if s.get("status") == "blocked" and not failed_upstream(s["id"], {s["id"]}):
            s["status"] = "todo"


def write_prompt(path, text, model):
    """Write a prompt for the Agent tool to `path`: its `PROMPT <file> model=<model>` line."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text + "\n")
    return f"PROMPT {path} model={model}"


def launch(p, m, s, retry=None):
    """Dispatch one story as phase-3-build.md's Dispatch says, and record it: its one line."""
    sid, model = safe_id(s["id"]), s.get("model") or "sonnet"
    safe_id(m["id"])
    if not (isinstance(model, str) and MODEL.fullmatch(model)):
        return f"FAILED {sid} model {model!r}: not a model name"
    if retry:
        if s.get("status") == "done":
            return f"SKIP {sid} done"
        kept = retire(p, m, s)
        if kept:
            return f"SKIP {sid} " + "; ".join(kept)
    elif sid not in p.ready(m):
        waits = [d for d in s.get("deps", []) + s.get("overlapAfter", [])
                 if next((x for x in m.get("stories", []) if x["id"] == d), {}).get("status") != "done"]
        why = (f"is {s.get('status')}" if s.get("status") != "todo" else "handed off" if sid in p.handed_off(m)
               else f"waits on {' '.join(waits)}")
        return f"SKIP {sid} {why}"
    trees, made = story_trees(p, m, s), []

    def undo():
        for src, tree in made:
            git_in(src, "worktree", "remove", "--force", tree)
            if not retry:
                git_in(src, "branch", "-D", f"story/{sid}")

    for name, src, tree, start in trees:
        if not src or not start:
            undo()
            return f"FAILED {sid} {name}: the milestone has no checkout or branch for it"
        os.makedirs(os.path.dirname(tree), exist_ok=True)
        ok, _, why = git_in(src, "worktree", "add", "-B" if retry else "-b", f"story/{sid}", "--end-of-options", tree, start)
        if not ok:
            undo()
            return f"FAILED {sid} worktree {name}: {why}"
        made.append((src, tree))
    text = story_prompt(p, m, s, retry)
    if dispatcher(p) == "paseo":
        model, home = paseo_provider(model), trees[0][2]
        title = f"{sid} · {s.get('title', '')}".rstrip(" ·")
        epic = next((e["id"] for e in p.epics() if m in e.get("milestones", [])), "")
        ws, why = paseo("workspace", "create", "--isolation", "local", "--path", home, "--title", title)
        run = None
        if ws:
            run, why = paseo("run", "-d", "--workspace", ws["workspaceId"], "--cwd", home, "--title", title,
                             "--provider", model, "--mode", "auto", "--label", f"epic={epic}", "--label", f"story={sid}",
                             "--env", f"PODIUM_DIR={p.root}", "--env", f"PODIUM_MILESTONE={m['id']}",
                             "--env", f"PODIUM_STORY={sid}", text)
        if not run:
            if ws:
                paseo("workspace", "archive", ws["workspaceId"])
            undo()
            return f"FAILED {sid} paseo: {why}"
        agent = {"backend": "paseo", "id": run["agentId"], "workspace": ws["workspaceId"]}
        line = f"LAUNCHED {sid} paseo agent={run['agentId'][:8]} model={model}"
    else:
        agent, line = {"backend": "agent"}, write_prompt(os.path.join(p.dir, "stories", m["id"], f"{sid}.prompt"), text, model)
    s.update(status="working", attempts=(s.get("attempts") or 0) + 1, agent=agent, branch=f"story/{sid}",
             worktrees={name: tree for name, _, tree, _ in trees}, startedAt=NOW())
    unblock(m)
    if retry:
        p.event("retry", m["id"], sid, attempt=s["attempts"], reason=retry.splitlines()[0][:200])
    p.event("dispatched", m["id"], sid, backend=agent["backend"], model=model)
    p.save()
    return line


def moved_target(p, mid):
    """Where milestone `mid`'s scope ended up: `movedTo` followed to the end, stopping where a cycle closes."""
    by_id = {x.get("id"): x for x in p.milestones()}
    seen = [mid]
    while (by_id.get(seen[-1]) or {}).get("status") == "moved":
        to = by_id[seen[-1]].get("movedTo")
        if not isinstance(to, str) or to in seen:
            break
        seen.append(to)
    return seen[-1]


def awaited(p, m):
    """The milestones `m` waits for that haven't landed, a moved one as `<its final target> (was <it>)`, while the user
    hasn't chosen to go ahead without them."""
    if m.get("waitsForAck"):
        return []
    gone = {x.get("id") for x in p.milestones() if x.get("status") in ("done", "landed", "dropped")}
    waits = [w["milestone"] for w in m.get("waitsFor") or [] if isinstance(w, dict) and w.get("milestone")]
    return [target if target == w else f"{target} (was {w})"
            for w, target in ((w, moved_target(p, w)) for w in waits) if target not in gone and target != m.get("id")]


def cmd_launch(p, args):
    """Dispatch ready stories (phase-3-build.md, Dispatch) and record each.

    launch [<milestone>/]<story>... [--retry <reason, or @file>] [--force]
    A worktree on story/<id> beside the repo, then with this machine's dispatcher paseo a Paseo workspace and agent
    running the story prompt; records status, attempts, agent, branch, worktrees, startedAt and a `dispatched` event.
    --retry retires the last attempt first, starts the branch afresh and adds the reason to the prompt.
      LAUNCHED <id> paseo agent=<id> model=<provider>
      PROMPT <file> model=<model>          dispatcher agent: hand the file to the Agent tool
      SKIP <id> <why> | FAILED <id> <why>   nothing recorded, worktree undone
      DISPATCHER agent (podium dispatcher paseo to use Paseo)   once, a synced run this machine chose none for
    Launches nothing when a story's milestone is another person's, unless --force.
    """
    retry = args[args.index("--retry") + 1] if "--retry" in args else None
    ids = [a for a in args if a not in ("--retry", retry, "--force")]
    if not ids:
        sys.exit("launch [<milestone>/]<story>... [--retry <reason, or @file>] [--force]")
    if retry and retry.startswith("@"):
        with open(retry[1:]) as f:
            retry = f.read().strip()
    targets = [target.rpartition("/")[::2] for target in ids]
    for mid, sid in targets:
        require_owner(p, p.story(sid, mid or None)[0]["id"], "--force" in args)
    for mid in dict.fromkeys(p.story(sid, mid or None)[0]["id"] for mid, sid in targets):
        if awaited(p, p.milestone(mid)):
            print(f"NOTE {mid} is waiting for {' '.join(awaited(p, p.milestone(mid)))}; launching anyway")
    for mid, sid in targets:
        m, s = p.story(sid, mid or None)
        print(launch(p, m, s, retry))


# --- hand-offs: the prompts that pass a milestone's planning, quality gate and retro to a fresh subagent ----
HANDOFF_MODELS = {"plan": "opus", "ahead": "opus", "gate": "opus", "retro": "opus"}
FRICTION = {"retry", "failed", "conflict", "approval", "denied"}
FINDING_FIXES = "check|pointer|standard|delete|access|script|flag|brief|model|tool"


def planning_tree(p, m):
    """The worktree that has the milestone's branch checked out, else None."""
    return checked_out(p.repo, m["branch"]) if m.get("branch") else None


def ledger(p, m):
    """deep-plan's ledger of a milestone: .deep-plan/state.md in the worktree of its branch, else the run's."""
    tree = planning_tree(p, m)
    return os.path.join(tree, ".deep-plan", "state.md") if tree else os.path.join(p.root, "state.md")


def handoff_rules(p, ends):
    """phase-1-plan.md's Hand-off bullets, with the user's mode as it is now and `ends`, when to return."""
    mode = human.availability()["mode"]
    ask = ("stop and return it (the question, 2–4 options, the recommended one first) without asking it"
           if mode in ("available", "mobile") else "record it as an assumption and go on")
    return [f"- The user is {mode} now (`{podium_cli(p.root)} human`). A question: {ask}.",
            "- Start no background agent: they die when you return. Name the background work deep-plan would start "
            "(research, a draft while a question waits) in your reply instead.",
            f"- {ends}"]


def milestone_events(p, mid):
    """events.jsonl's lines for milestone `mid`, oldest first, skipping lines that aren't JSON objects."""
    try:
        with open(os.path.join(p.dir, "events.jsonl")) as f:
            lines = [l for l in f if l.strip()]
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("milestone") == mid:
            events.append(e)
    return sorted(events, key=lambda e: str(e.get("at") or ""))


def friction(events):
    """The events a retro looks into: a story retried or failed, a merge conflict, a story stopped on a permission
    prompt (approval, or denied while the user was away), a quality gate whose verdict wasn't pass."""
    return [e for e in events if e.get("type") in FRICTION
            or e.get("type") == "gate" and e.get("verdict") not in (None, "pass")]


def retro_text(p, m, named, book, snags):
    mid, cli = safe_id(m["id"]), podium_cli(p.root)
    start = next((e["at"] for e in milestone_events(p, m["id"]) if e.get("at")), "7d")
    stories = [t for s in m.get("stories") or [] for _, _, t, _ in story_trees(p, m, s)]
    cwds = list(dict.fromkeys(os.path.abspath(c) for c in [p.repo, planning_tree(p, m), *stories] if c))
    tokens = f"{cli} tokens --since {shlex.quote(start)} " + " ".join(f"--cwd {shlex.quote(c)}" for c in cwds)
    return [f"Run a retro on {named}, which has landed: find what made it cost more than it should, so the skills and "
            "agents behind it stop repeating it. Edit nothing; record findings only.", "",
            "Its friction, from events.jsonl:"] + [f"- {json.dumps(e, ensure_ascii=False)}" for e in snags] + [
            "", "Read:",
            f"- its events: the lines of {os.path.join(p.dir, 'events.jsonl')} whose milestone is {mid}",
            f"- its ledger, {book}",
            f"- its stories' progress files, {os.path.join(p.dir, 'stories', mid, '*.progress')}",
            f"- where its tokens went: `{tokens}`", "",
            f"First run `{cli} findings --all`: a problem already there keeps its key.", "",
            "- Every finding cites a specific moment: an events line, a story id, a sha, or a session and tool call.",
            "- A mechanical mistake → fix `check`; a judgement call → `standard`; missing information → `pointer` or "
            "`access`.",
            "- Fix with a check, a pointer or a script; always-on prose is never the fix. Deleting an instruction that "
            "changes nothing is a fix too (`delete`).",
            "- No findings is a valid answer.", "",
            "Record each finding with:",
            f"  {cli} finding add --key <kebab-slug> --kind retro|tokens --target <skill, podium, or repo:<name>> "
            f"--title \"<one line>\" --moment \"<the evidence>\" --fix {FINDING_FIXES} --severity high|normal "
            f"[--saving <tokens/week, tokens kind only>] --milestone {mid}",
            "",
            "Reply with the FINDING lines it printed only, or `no findings`."]


def handoff_text(p, m, kind):
    mid, tree = safe_id(m["id"]), planning_tree(p, m)
    epic = next((e.get("id") for e in p.epics() if m in e.get("milestones", [])), "?")
    named, book = f"milestone {mid} ({m.get('title', '')}) of epic {epic}", ledger(p, m)
    if kind == "retro":
        return retro_text(p, m, named, book, friction(milestone_events(p, m["id"])))
    orchestrated = (f"{os.path.join(p.dir, 'podium.json')} exists, so deep-plan's Orchestrated runs rules apply; "
                    f"run podium as `{podium_cli(p.root)}`.")
    if kind == "plan":
        start = (f"Resume `/deep-plan` for {named} from its ledger, {book} (it names the phase)." if os.path.isfile(book)
                 else f"Start `/deep-plan` for {named} in {tree or p.repo}; its ledger will be {book}.")
        return [start, orchestrated, ""] + handoff_rules(
            p, "Return at the Phase 2 checkpoint, at the next context reset, or with a question, in at most 8 lines: "
               "the phase reached, the files written, the background work wanted, the question if any.")
    base = milestone_repo(p, m)["base"]
    if kind == "ahead":
        if tree:
            where = f"in its planning worktree {tree}, from its ledger, {book}"
        else:
            branch = "plan/" + "-".join(filter(None, [mid, re.sub(r"[^a-z0-9]+", "-", m.get("title", "").lower()).strip("-")[:40]]))
            plan_tree = os.path.join(os.path.dirname(p.repo), f"{os.path.basename(p.repo)}-plan-{mid}")
            where = (f"in its own worktree on its own planning branch, `git -C {shlex.quote(p.repo)} worktree add "
                     f"{shlex.quote(plan_tree)} -b {branch} {branch_name(base) if base else '<base>'}`, so it keeps its "
                     "own ledger and checkpoint commits")
        return [f"Run `/deep-plan` for {named} through its Phase 2 checkpoint, documents only, {where}. Read "
                f"`Reservations` in the main ledger, {os.path.join(p.root, 'state.md')}, first.",
                f"Write nothing under {p.root}: the orchestrator records the milestone from your reply.", "",
                "- Shared numbers: a new value from a sequence the whole project draws from (type and slot ids, enum "
                f"codes, edit groups, migration numbers, ports) goes in as a placeholder `«<kind>:{mid}:<n>»`, since the "
                "other planners are picking at the same time."] + handoff_rules(
            p, "Return at the Phase 2 checkpoint, at the next context reset, or with a question, in at most 8 lines: "
               "the phase reached, the files written, its branch, every placeholder, the background work wanted, the "
               "question if any.")
    return [f"Run `/deep-plan` for {named} from its Phase 3 quality gate (`~/.claude/skills/deep-plan/phase-3-exec.md`, "
            f"section \"Quality gate\") on through its Phases 4, 5 and 6, from its ledger, {book}. Start its review "
            "subagents in the foreground.", orchestrated + " Keep the milestone's `phase` and `needsYou` current.", ""] + (
        [f"Branch: {m['branch']} on {base}, worktree {tree or p.repo}", ""] if m.get("branch") else []) + handoff_rules(
        p, "Return at each sign-off gate, question or context reset, and once landed, in at most 8 lines: the gate's "
           "counts and findings file, each criterion's pass, the PR, the landed sha.")


def cmd_handoff(p, args):
    """<milestone> plan|ahead|gate|retro: the prompt that hands a milestone to a fresh subagent, written to
    podium/handoffs/<milestone>-<kind>.md: `plan` resumes deep-plan's planning (phase-1-plan.md, Hand-off), `ahead`
    plans a later milestone while another builds (Planning ahead), `gate` runs deep-plan from its quality gate to its
    landing (phase-4-handback.md), `retro` records findings on a landed milestone's friction (phase-5-retro.md).
      PROMPT <file> model=<model>          hand the file to the Agent tool
      SKIP no friction                     retro only: nothing in its events to look into; no file written
    """
    if len(args) != 2 or args[1] not in HANDOFF_MODELS:
        sys.exit(f"handoff <milestone> {'|'.join(HANDOFF_MODELS)}")
    m, kind = p.milestone(args[0]), args[1]
    if kind == "retro" and not friction(milestone_events(p, m["id"])):
        return print("SKIP no friction")
    path = os.path.join(p.dir, "handoffs", f"{safe_id(m['id'])}-{kind}.md")
    print(write_prompt(path, "\n".join(handoff_text(p, m, kind)), HANDOFF_MODELS[kind]))


def cmd_land(p, args):
    """After `merge` printed MERGED: retire the story, release a hand-off, and with --next launch the next wave.

    land <story> | <milestone>/<story> [--next] [--force]
    Archives the story's Paseo workspace and removes its worktree; --next with the story's milestone's buildAll
    on and its wave complete launches that milestone's ready stories. Prints `LANDED <id>[; launched <ids> |
    ; wave waits on <ids> | ; wave held | ; buildAll off]`, then a line per PROMPT, KEPT worktree or failure. A milestone another
    person owns is refused unless --force.
    """
    target = next((a for a in args if a not in ("--next", "--force")), None)
    if not target:
        sys.exit("land <story> | <milestone>/<story> [--next] [--force]")
    mid, _, sid = target.rpartition("/")
    require_owner(p, p.story(sid, mid or None)[0]["id"], "--force" in args)
    m, s = p.story(sid, mid or None)  # claiming pulls, which replaces p.data
    if s.get("status") != "done":
        print(f"NOT-MERGED {sid} {s.get('status')}")
        sys.exit(1)
    extra = retire(p, m, s)
    if sid in p.handed_off(m):
        url, _ = podium_url(p)
        gone = url and http(f"{url}handoff/{safe_id(m['id'])}/{safe_id(sid)}", method="DELETE")
        extra.append(f"RELEASED {sid}" if gone else f"HANDOFF {sid} still held: no Podium answered")
    head = f"LANDED {sid}"
    if "--next" in args:
        p.refresh()  # retiring can take minutes: decide the wave from podium.json as it is now
        m = p.milestone(m["id"])
        busy = [x["id"] for x in m.get("stories", []) if x.get("status") in ("working", "approval")]
        if not m.get("buildAll"):
            head += "; buildAll off"
        elif awaited(p, m):
            head += "; wave held"
            extra.append(f"WAITING {m['id']} for {' '.join(awaited(p, m))}")
        elif busy:
            head += f"; wave waits on {' '.join(busy)}"
        else:
            out = [(r, launch(p, *p.story(r, m["id"]))) for r in p.ready(m)]  # each launch saves: look the story up afresh
            done = [r for r, line in out if line.split()[0] in ("LAUNCHED", "PROMPT")]
            head += f"; launched {' '.join(done)}" if done else "; nothing ready"
            extra += [line for _, line in out if not line.startswith("LAUNCHED")]
    print(head)
    for line in extra:
        print(line)


# --- peek: a story at a glance ------------------------------------------------------
STAGE = re.compile(r"^[A-Za-z_-]{1,32}$")
EPOCH = datetime.fromtimestamp(0, timezone.utc)


def stamp(iso):
    """An ISO time podium.json or a progress file recorded, as an aware datetime; None when it isn't one."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def age(t):
    """The time since `t` as `45s`, `14m`, `2h5m` or `3d4h`."""
    s = max(0, int((datetime.now(timezone.utc) - t).total_seconds()))
    if s < 3600:
        return f"{s}s" if s < 60 else f"{s // 60}m"
    return f"{s // 3600}h{s % 3600 // 60}m" if s < 86400 else f"{s // 86400}d{s % 86400 // 3600}h"


def progress_lines(p, m, s):
    """[(time, stage, note)] of the story's progress file, oldest first, skipping lines not shaped as `log` writes."""
    if not (ID.fullmatch(str(m.get("id"))) and ID.fullmatch(str(s.get("id")))):
        return []
    try:
        with open(os.path.join(p.dir, "stories", m["id"], f"{s['id']}.progress")) as f:
            rows = [line.rstrip("\n").split(" ", 2) for line in f]
    except OSError:
        return []
    return [(stamp(r[0]), r[1], r[2] if len(r) > 2 else "") for r in rows
            if len(r) > 1 and stamp(r[0]) and STAGE.fullmatch(r[1])]


def peek_stage(lines):
    """`<previous stage>→<last stage> <age> ago`, a repeated stage counted once."""
    if not lines:
        return "progress -"
    at, last, _ = lines[-1]
    before = next((stage for _, stage, _ in reversed(lines) if stage != last), None)
    return f"{before + '→' if before else ''}{last} {age(at)} ago"


def peek_gates(m, s):
    """`gates <repo>✓|✗ …` of the contract commands merge last ran for this attempt of the story."""
    started = stamp(s.get("startedAt"))
    this_attempt = lambda c: not started or (stamp(c.get("at")) or EPOCH) >= started
    ran = [c for c in (m.get("quality") or {}).get("contract") or [] if c.get("story") == s["id"] and "ok" in c and this_attempt(c)]
    return "gates " + (" ".join(f"{c.get('repo') or 'contract'}{'✓' if c['ok'] else '✗'}" for c in ran) or "-")


def peek_commit(s, lines):
    """`committed <repo>:<sha> …` from the commits merge recorded, else the COMMITTED line of the story's current
    attempt (the lines since its last STARTED); `commit -` without either."""
    recorded = {}
    for repo, c in story_commits(s):
        sha = c.get("sha") if isinstance(c, dict) else None
        if isinstance(sha, str) and SHA.fullmatch(sha):
            recorded[repo] = sha
    if recorded:
        return "committed " + " ".join(f"{r + ':' if r else ''}{sha[:7]}" for r, sha in recorded.items())
    starts = [i for i, (_, stage, _) in enumerate(lines) if stage == "STARTED"]
    note = next((n for _, stage, n in reversed(lines[starts[-1] if starts else 0:]) if stage == "COMMITTED"), None)
    if note is None:
        return "commit -"
    shas = [x for x in note.split() if re.fullmatch(r"(?:[A-Za-z0-9._-]{1,64}:)?[0-9a-f]{4,64}", x)]
    return "committed " + (" ".join(x[:x.rfind(":") + 8] for x in shas) or "?")


def process_cwds():
    """The working directory of every process lsof can see, or None when it can't run."""
    try:
        r = subprocess.run(["lsof", "-d", "cwd", "-Fn"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return [line[1:] for line in r.stdout.splitlines() if line.startswith("n")] if r.stdout or not r.returncode else None


def peek_agent(p, m, s, look):
    """`agent alive|idle|dead|<paseo status> (paseo <id>)` from `paseo ls`, `agent local (<n> procs in worktree)`
    from the processes working in its worktrees, `agent handed off`, or `agent -`. `look(kind)` asks Paseo or lsof
    once per peek."""
    a = s.get("agent") or {}
    if a.get("backend") == "paseo" and a.get("id"):
        name = f"paseo {a['id'][:8] if PASEO_ID.fullmatch(str(a['id'])) else '?'}"
        agents, why = look("paseo")
        if agents is None:
            return f"agent ? ({name}: {why[:60]})"
        status = agents.get(a["id"], "dead")
        status = {"running": "alive"}.get(status, status if STAGE.fullmatch(str(status)) else "?")
        return f"agent {status} ({name})"
    if a.get("backend") == "agent":
        cwds = look("lsof")
        if cwds is None:
            return "agent local"
        trees = [t for t in (checkout_path(p, x) for x in (s.get("worktrees") or {}).values() if isinstance(x, str)) if t]
        n = sum(1 for c in cwds if any(c == t or c.startswith(t + os.sep) for t in trees))
        return f"agent local ({n} procs in worktree)"
    return "agent handed off" if s["id"] in p.handed_off(m) else "agent -"


def find_any_story(p, ident):
    """(milestone, story, why not) for `<story>` of the active milestone, else of the one milestone that has it, or
    `<milestone>/<story>`."""
    m, s = find_story(p, ident)
    if s or "/" in ident:
        return m, s, None if s else "unknown"
    hits = [(m, s) for m in p.milestones() for s in m.get("stories", []) if s.get("id") == ident]
    if len(hits) == 1:
        return (*hits[0], None)
    return None, None, f"ambiguous: {' '.join(m['id'] + '/' + ident for m, _ in hits)}" if hits else "unknown"


def cmd_peek(p, args):
    """[<milestone>/]<story>...: one line per story, read-only.

      <milestone>/<id> <status>[ <age>] · <stage>→<stage> <age> ago · gates <repo>✓|✗… · agent <state> · committed <sha>
    status age: since startedAt while working, since finishedAt once done; stage: the progress file's last two
    stages; gates: the contract merge last ran for this attempt; agent: alive, idle, dead or Paseo's status for a
    Paseo agent, the processes working in its worktrees for an Agent tool one; commit: merge's record, else the
    current attempt's COMMITTED line. `-` where there is nothing. `PEEK <id> unknown | ambiguous: <ids>` otherwise.
    """
    if not args:
        sys.exit("peek [<milestone>/]<story>...")
    cache = {}

    def look(kind):
        if kind not in cache:
            if kind == "paseo":
                got, why = paseo("ls", "-g")
                cache[kind] = ({x.get("id"): x.get("status") for x in got if isinstance(x, dict)}, None) \
                    if isinstance(got, list) else (None, why or "paseo answered no list")
            else:
                cache[kind] = process_cwds()
        return cache[kind]

    for ident in args:
        m, s, why = find_any_story(p, ident)
        if why:
            print(f"PEEK {ident} {why}")
            continue
        status, lines = s.get("status") or "?", progress_lines(p, m, s)
        started, finished = stamp(s.get("startedAt")), stamp(s.get("finishedAt"))
        if status in ("working", "approval") and started:
            status += f" {age(started)}"
        elif status == "done" and finished:
            status += f" {age(finished)} ago"
        print(" · ".join([f"{m['id']}/{s['id']} {status}", peek_stage(lines), peek_gates(m, s),
                          peek_agent(p, m, s, look), peek_commit(s, lines)]))


# --- the start of a turn: base branches, landings, the Podium, Asana, requests ----
def fast_forward(name, cwd, base):
    """Move the local `base` to origin/<base> when that is a strict fast-forward, in its checkout only when the
    checkout is clean, or as a bare ref when no worktree has it; a line for what moved or why it didn't."""
    branch_name(base)
    local, remote = sha_of(cwd, f"refs/heads/{base}"), sha_of(cwd, f"refs/remotes/origin/{base}")
    if not local or not remote or local == remote:
        return []
    behind = int(git_in(cwd, "rev-list", "--count", f"{local}..{remote}")[1] or 0)
    ahead = int(git_in(cwd, "rev-list", "--count", f"{remote}..{local}")[1] or 0)
    if not behind:
        return []
    if ahead or not git_in(cwd, "merge-base", "--is-ancestor", local, remote)[0]:
        return [f"BEHIND {name} {base} {behind}: diverged, {ahead} local commits"]
    tree = checked_out(cwd, base)
    if tree is None:
        ok, _, why = git_in(cwd, "update-ref", f"refs/heads/{base}", remote, local)  # only if it still points at local
    elif not os.path.isdir(tree):
        return [f"BEHIND {name} {base} {behind}: checked out in {tree}, which is missing"]
    elif git_in(tree, "status", "--porcelain", "--untracked-files=no")[1]:  # an untracked file in the way stops the merge itself
        return [f"BEHIND {name} {base} {behind}: {tree} has changes"]
    else:
        ok, _, why = git_in(tree, "merge", "--ff-only", "--quiet", remote)
    if not ok:
        return [f"BEHIND {name} {base} {behind}: {why}"]
    return [f"FF {name} {base} {local[:7]}..{remote[:7]} ({behind} commits)"]


def sync_bases(p):
    """Fetch every repo of the run once, then fast-forward each base branch: (lines, repos fetched)."""
    repos = [(os.path.basename(p.repo), p.repo, None, True)] if git_in(p.repo, "rev-parse", "--git-dir")[0] else []
    for m in p.milestones():
        live = m.get("status") not in CLOSED
        repos += [(name, checkout(p, r["path"]), r.get("base"), live) for name, r in (m.get("repos") or {}).items() if r.get("path")]
    lines, fetched, bases = [], {}, set()
    for name, path, base, live in repos:
        if not os.path.isdir(path):
            lines += [f"MISSING {name} {path}"] if live else []
            continue
        ok, common, _ = git_in(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
        if not ok:
            continue
        if common not in fetched:
            fetched[common] = git_in(path, "fetch", "--quiet", "origin", timeout=180)
            if not fetched[common][0]:
                lines.append(f"FETCH-FAILED {name}: {fetched[common][2]}")
        if not fetched[common][0]:
            continue
        base = base or (git_in(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")[1].split("/", 1)[-1] or None)
        if base and (common, base) not in bases:
            bases.add((common, base))
            lines += fast_forward(name, path, base)
    return lines, len(fetched)


def carried_work(m, r):
    """Whether the milestone's branch holds work to land: a story's commits, or a PR."""
    return bool(r.get("pr")) or any(s.get("commits") for s in m.get("stories", []))


def landing(p, m, r, merged):
    """(sha, unix time, range of the branch's own commits or None) when the milestone landed on its base, else None.
    Landed: the branch's tip is on origin/<base> and the branch carried work, or its PR merged (`merged`: gh's
    answer, {} when gh couldn't say how)."""
    path = r["path"]
    here = os.path.isdir(path) and r.get("base") and r.get("branch")
    base = f"refs/remotes/origin/{r.get('base')}"
    tip = here and (sha_of(path, f"refs/heads/{r['branch']}") or sha_of(path, f"refs/remotes/origin/{r['branch']}"))
    if tip and carried_work(m, r) and sha_of(path, base) and git_in(path, "merge-base", "--is-ancestor", tip, base)[0]:
        # the first commit on the base's first-parent line that holds the tip: the merge, or the tip itself
        line = git_in(path, "rev-list", "--first-parent", "--ancestry-path", f"{tip}..{base}")[1].split()
        sha = line[-1] if line and sha_of(path, f"{line[-1]}^1") != tip else tip
        return sha[:10], int(git_in(path, "show", "-s", "--format=%ct", sha)[1] or 0), f"{sha}^1..{tip}" if sha != tip else None
    if merged is not None:
        sha = (merged.get("mergeCommit") or {}).get("oid") or ""
        at = datetime.fromisoformat(merged["mergedAt"].replace("Z", "+00:00")).timestamp() if merged.get("mergedAt") else 0
        return sha[:10], int(at), tip and f"{base}..{tip}"
    return None


def trailer_commits(p, own):
    """{story id: [commit]} of the commits in range `own`, by their `Story: <id>` trailer."""
    ok, out, _ = git_in(p.repo, "log", "--no-merges", "--format=%H%x1f%(trailers:key=Story,valueonly,separator=%x2C)", own)
    by_sha = {}
    for line in out.splitlines() if ok else []:
        sha, _, ids = line.partition("\x1f")
        by_sha[sha[:10]] = [i.strip() for i in ids.split(",") if i.strip()]
    found = {}
    for c in git_commits(p, own) if by_sha else []:
        for sid in by_sha.get(c["sha"], []):
            found.setdefault(sid, []).append({k: v for k, v in c.items() if k != "at"})
    return found


def refusal(p, mid, force):
    """require_owner's refusal of milestone `mid` as text, or None when this person may change it."""
    try:
        require_owner(p, mid, force, claim=False)
    except SystemExit as e:
        return str(e.code).removeprefix("podium: ")
    return None


def record_landings(p, gh, force=False):
    """Milestones that landed on their base since podium.json last saw them, recorded `done`: a line each. A landing of
    a milestone this person may not change is only reported."""
    lines = []
    for m in p.milestones():
        if m.get("status") in CLOSED or not m.get("branch"):
            continue
        got = landing(p, m, milestone_repo(p, m), gh.get(m["id"]))
        if not got:
            continue
        why = refusal(p, m["id"], force)
        if why:
            lines.append(f"SKIP-LANDED {m['id']}: {why}")
            continue
        sha, at, own = got
        filled = set()
        for sid, commits in (trailer_commits(p, own) if own else {}).items():
            s = next((s for s in m.get("stories", []) if s["id"] == sid), None)
            if not s or s.get("commits"):
                continue
            s["commits"] = commits
            if s.get("status") != "dropped":
                s["status"] = "done"
            filled.add(sid)
        subject = git_in(p.repo, "show", "-s", "--format=%s", "--end-of-options", sha)[1] if sha else ""
        p.event("landed", m["id"], at=UTC(at) if at else None, sha=sha, subject=subject)
        m.update(status="done", phase="land", landedSha=sha,
                 shippedAt=datetime.fromtimestamp(at).strftime("%Y-%m-%d") if at else datetime.now().strftime("%Y-%m-%d"))
        if p.active().get("milestone") == m["id"]:
            p.own()["active"] = None
        lines.append(f"LANDED {m['id']} {sha[:7]} {m['shippedAt']}; commits for {len(filled)} stories from trailers")
        a = m.get("asana") or {}
        if a.get("gid") and not a.get("completed"):
            lines.append(f"ACT asana-complete {m['id']} {a['gid']}" if re.fullmatch(r"[0-9]+", str(a["gid"]))
                         else f"refused asana gid {a['gid']!r}: not all digits")
    return lines


def links_asana(p):
    return bool((p.data.get("project") or {}).get("asana") or any(x.get("asana") for x in p.epics() + p.milestones()))


def asana_lines(p):
    try:
        from podium_dashboard.plugins import asana
    except ImportError as e:
        return [f"ASANA-UNAVAILABLE {e}"]
    return asana.refresh(p)


def unanswered(p, line):
    """False for an `ACT asana-done` whose milestone was dropped or moved, or keeps its Asana task open meanwhile."""
    words = line.split()
    if words[:2] != ["ACT", "asana-done"] or len(words) < 3:
        return True
    m = next((m for m in p.milestones() if m.get("id") == words[2]), {})
    return not (m.get("status") in ("dropped", "moved") or (m.get("asana") or {}).get("keep"))


PODIUM = [os.environ["PODIUM_TOOL"]] if os.environ.get("PODIUM_TOOL") else [sys.executable, "-m", "podium_dashboard"]
UPDATE_EVERY = 6 * 3600


def update_stamp_path():
    return os.path.join(os.path.dirname(human.HUMAN_FILE), "update.json")


def due(key):
    """Whether `key` was last checked over UPDATE_EVERY ago; records this check."""
    path = update_stamp_path()
    try:
        with open(path) as f:
            stamps = json.load(f)
    except (OSError, ValueError):
        stamps = {}
    if not isinstance(stamps, dict):
        stamps = {}
    now = datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(stamps[key]["at"])
        if 0 <= (now - last).total_seconds() < UPDATE_EVERY:
            return False
    except (KeyError, TypeError, ValueError):
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_atomic(path, json.dumps({**stamps, key: {"at": now.isoformat(timespec="seconds")}}))
    return True


def update_skills():
    """Fast-forward the clone holding this file when it is on its default branch with a clean skill folder."""
    folder = os.path.dirname(os.path.realpath(os.environ.get("PODIUM_EXTENSION_FILE") or __file__))

    def run(*args):
        return subprocess.run(git_argv(*args), cwd=folder, capture_output=True, text=True, timeout=30)

    top = run("rev-parse", "--show-toplevel")
    if top.returncode:
        return
    top = os.path.realpath(top.stdout.strip())
    if not due(f"skills:{top}"):
        return
    default = run("symbolic-ref", "--short", "refs/remotes/origin/HEAD").stdout.strip().removeprefix("origin/")
    branch = run("branch", "--show-current").stdout.strip()
    if not default:
        return print("SKIP skills no origin/HEAD")
    if branch != default:
        return print(f"SKIP skills on {branch or 'a detached HEAD'}, not {default}")
    if run("status", "--porcelain", "--", ".").stdout.strip():
        return print("SKIP skills folder has changes")
    old = run("rev-parse", "HEAD").stdout.strip()
    pull = run("pull", "--ff-only", "--quiet")
    if pull.returncode:
        return print(f"WARN skills {pull.stderr.strip().splitlines()[-1] if pull.stderr.strip() else 'pull failed'}")
    new = run("rev-parse", "HEAD").stdout.strip()
    if new != old:
        print(f"UPDATED skills {old[:7]}→{new[:7]}")
        print("RELOAD skills")


def pass_through(label, *args, timeout, cwd=None):
    """Run `podium <args>` in `cwd` and print its lines; an older podium without the command prints nothing, and a
    failure a `WARN <label>` line. Never fails."""
    try:
        r = subprocess.run([*PODIUM, *args], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    except Exception as e:
        return print(f"WARN {label} {e}")
    if r.returncode and "unknown command" in r.stdout + r.stderr:
        return
    for line in r.stdout.splitlines():
        print(line)
    if r.returncode and not r.stdout.strip():
        print(f"WARN {label} {(r.stderr.strip().splitlines() or [f'{args[0]} failed'])[-1]}")


def self_update(p):
    """The start of a turn: update this skill's clone, then the podium tool, passing its lines through. Never fails."""
    try:
        update_skills()
    except Exception as e:
        print(f"WARN skills {e}")
    pass_through("podium", "self-update", timeout=300)


def cmd_turn(p, args):
    """The start of a turn, one line per fact: sync's pull, base branches, PRs, landings, status, the Podium, requests.

    turn [--force]
    First self_update's lines (UPDATED|SKIP|WARN skills|podium …, RELOAD skills, RESTART server), then
      RECUR <key> ×<runs> — <title>                 an open finding recurring across runs, at most daily
    then `podium sync pull`'s line, then
      FF <repo> <base> <old>..<new> (<n> commits)   base fast-forwarded to origin
      BEHIND <repo> <base> <n>: <why>               left alone: diverged, or its checkout has changes
      FETCH-FAILED <repo>: <why> | SYNC <n> repos up to date
      PR <milestone> #<n> <state> (was <old>) | PR-ERROR …
      LANDED <milestone> <sha> <date>; …            landed on its base since podium.json saw it: recorded done
      SKIP-LANDED <milestone>: <why>                landed, but another person's (or unclaimed): left to them; --force records it
      ACT asana-complete <milestone> <gid>          a landed milestone's subtask to complete
      refused asana gid <gid>: not all digits       the same, its gid not an Asana gid: nothing to complete
    then `status`; PODIUM up <url> watching|not watching, or PODIUM down; the Asana plugin's refresh lines when
    anything links Asana; and each request in requests.jsonl no turn or watcher passed on:
      ACT <confirm|reverse|asana|asana-done> <id> [note=…]   the user's answers: act on them
      LIST <action> [<id>] [note=…]                         the rest: report them (share: share the run)
    A base branch moves only by a strict fast-forward: in the worktree that has it checked out when it has no
    tracked changes, or as a bare ref when none has it. A milestone lands when its branch tip, carrying work
    (story commits or a PR), is on origin/<base> (`base`, else origin's default branch), or its PR merged; it is
    recorded done with landedSha, shippedAt, its stories' commits from their `Story: <id>` trailers, and a
    `landed` event.
    """
    self_update(p)
    pass_through("findings", "findings", "--recur", timeout=120, cwd=p.root)
    pulled = sync.pull(p)
    print(pulled)
    if pulled.startswith("PULLED"):
        p.load()
    out, fetched = sync_bases(p)
    gh = {}
    for m in p.milestones():
        pr = m.get("pr")
        if m.get("status") in CLOSED or not pr or not pr.get("number"):
            continue
        if pr.get("state") == "merged":  # merged before this turn: gh only says how
            gh[m["id"]] = gh_pr(p, pr["number"])[0] or {}
            continue
        state, old, got, why = refresh_pr(p, m, pr)
        if why:
            out.append(f"PR-ERROR {m['id']} #{pr['number']}: {why}")
        elif state != old:
            out.append(f"PR {m['id']} #{pr['number']} {state} (was {old})")
        if state == "merged":
            gh[m["id"]] = got
    out += record_landings(p, gh, "--force" in args)
    for line in out or [f"SYNC {fetched} repos up to date"]:
        print(line)
    cmd_status(p, [])
    url, info = podium_url(p)
    print(f"PODIUM up {info.get('lan') or url} " + ("watching" if info.get("watching") else "not watching") if url else "PODIUM down")
    if links_asana(p):
        for line in asana_lines(p):
            print(line)
    for line in queued_requests(p):
        if unanswered(p, line):
            print(line)
    p.save()


COMMANDS = {"approve": cmd_approve, "commits": cmd_commits, "merge": cmd_merge, "prs": cmd_prs,
            "backfill": cmd_backfill, "brief": cmd_brief, "dispatcher": cmd_dispatcher, "launch": cmd_launch,
            "land": cmd_land, "peek": cmd_peek, "turn": cmd_turn, "breakdown": cmd_breakdown, "handoff": cmd_handoff}
SHARE_STEPS = ["Clone this run's repo if you haven't: git clone <url>",
               "Install the podium tool (pip3 install --user git+https://github.com/warriv93/podium-dashboard) and the "
               "orchestrate-deep-plans skill (clone https://github.com/warriv93/deep-skills and run its ./install.sh; "
               "see its README)",
               "In your clone, start claude and run /orchestrate-deep-plans join {ref}",
               "Claim a milestone: podium claim <id>"]
