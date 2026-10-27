#!/usr/bin/env python3
"""The deterministic steps of /deep-improve, one line per fact.

    improve.py remotes                          --remote <url> ... for `podium findings --all`
    improve.py select [--date D] [--force]      stdin: `podium findings --all` lines → PICK/SKIP lines, writes <D>.json
    improve.py baseline <n> <PATTERN line>      a tokens fix's pattern before the fix
    improve.py checks [--days 5]                CHECK lines: tokens fixes pushed ≥ days ago, not yet re-measured
    improve.py compare <date> <n>               stdin: `podium tokens --since <pushed>` → KEPT|REVERT
    improve.py revert <date> <n>                adds a revert of that pushed fix to the newest report
    improve.py entry <n>... [--report D]        ENTRY lines, for approve/reject
    improve.py decide <n> pushed <sha>|rejected|failed [<why>] [--report D]
    improve.py report                           the newest report's .md and .json paths

entry and decide default to the newest report.

Reports live in ~/.podium/improve/ (`--home` moves ~/.podium); config in ~/.podium/improve.json.
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone

DEFAULT_CAP = 5
PODIUM_FALLBACK = "~/gitrepos/warriv93/podium-dashboard"

FINDING = re.compile(
    r"^FINDING (?P<key>\S+) ×(?P<runs>\d+) (?P<status>open|resolved \S+|wontfix) (?P<kind>\S+) (?P<target>\S+) "
    r"(?P<severity>high|normal)(?: ~(?P<saving>[\d.]+[kKmM]?)/wk)? — (?P<title>.*)$")
PATTERN = re.compile(r"^PATTERN (?P<kind>\S+) ×(?P<count>\d+) ~(?P<tokens>[\d.]+[kKmM]?)/wk (?P<normalized>.*)$")


def amount(text):
    if not text:
        return 0
    scale = {"k": 1_000, "m": 1_000_000}.get(text[-1].lower(), 1)
    return int(float(text.rstrip("kKmM")) * scale)


def parse_findings(lines):
    out = []
    for line in lines:
        m = FINDING.match(line.strip())
        if m:
            f = m.groupdict()
            f["runs"], f["saving"] = int(f["runs"]), amount(f["saving"])
            out.append(f)
    return out


def eligible(f):
    return f["status"] == "open" and (f["runs"] >= 2 or f["severity"] == "high")


def rank(f):
    return (-f["runs"] * max(f["saving"], 1), f["severity"] != "high", -f["runs"], f["key"])


def git(cwd, *args):
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def toplevel(path):
    return git(path, "rev-parse", "--show-toplevel") if os.path.isdir(path) else None


def podium_checkout(pip_show=None, fallback=PODIUM_FALLBACK):
    if pip_show is None:
        r = subprocess.run([sys.executable, "-m", "pip", "show", "-f", "podium-dashboard"], capture_output=True, text=True)
        pip_show = r.stdout if r.returncode == 0 else ""
    location = re.search(r"^Location: (.+)$", pip_show, re.M)
    for name in re.findall(r"^\s+(\S+\.dist-info/direct_url\.json)$", pip_show, re.M):
        try:
            with open(os.path.join(location.group(1), name)) as fh:
                url = json.load(fh).get("url", "")
        except (OSError, ValueError, AttributeError):
            continue
        if url.startswith("file://") and toplevel(url[len("file://"):]):
            return toplevel(url[len("file://"):])
    return toplevel(os.path.expanduser(fallback))


def resolve_target(target, skills_dir="~/.claude/skills", podium=podium_checkout):
    """(repo toplevel, None) or (None, why it is skipped)."""
    if target.startswith("repo:"):
        return None, "project repo %s: fixes there follow that repo's own standards" % target[len("repo:"):]
    if target == "podium":
        repo = podium()
        return (repo, None) if repo else (None, "no podium-dashboard checkout found")
    link = os.path.join(os.path.expanduser(skills_dir), target)
    repo = toplevel(os.path.realpath(link)) if os.path.exists(link) else None
    if repo:
        return repo, None
    return None, "skill %s is not installed in %s or not in a git checkout" % (target, skills_dir)


def default_branch(repo):
    ref = git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ref:
        return ref.split("/", 1)[1]
    head = git(repo, "ls-remote", "--symref", "origin", "HEAD") or ""
    m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", head, re.M)
    return m.group(1) if m else None


def load_config(home):
    path = os.path.join(home, "improve.json")
    cfg = {}
    if os.path.exists(path):
        with open(path) as fh:
            cfg = json.load(fh)
    remotes = cfg.get("remotes") or ([cfg["findings"]] if cfg.get("findings") else [])
    return {"remotes": remotes, "cap": int(cfg.get("cap", DEFAULT_CAP))}


def reports(home):
    return sorted(glob.glob(os.path.join(home, "improve", "[0-9]*-[0-9]*-[0-9]*.json")))


def read(path):
    with open(path) as fh:
        return json.load(fh)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def awaiting(home):
    keys = {}
    for path in reports(home):
        for e in read(path)["entries"]:
            if "decision" not in e:
                keys[e["key"]] = os.path.basename(path)[:-len(".json")]
    return keys


def select(findings, cap, home, today, resolve=None, branch_of=None):
    resolve, branch_of = resolve or resolve_target, branch_of or default_branch
    pending = awaiting(home)
    picks, skips = [], []
    for f in sorted(filter(eligible, findings), key=rank):
        if f["key"] in pending:
            skips.append((f["key"], "drafted %s, awaiting approve or reject" % pending[f["key"]]))
            continue
        repo, why = resolve(f["target"])
        if why:
            skips.append((f["key"], why))
            continue
        branch = "improve/" + f["key"]
        if git(repo, "rev-parse", "--verify", "-q", "refs/heads/" + branch):
            skips.append((f["key"], "branch %s already exists in %s" % (branch, repo)))
            continue
        default = branch_of(repo)
        if not default:
            skips.append((f["key"], "no default branch on origin of %s" % repo))
            continue
        if len(picks) == cap:
            skips.append((f["key"], "over the cap of %d" % cap))
            continue
        picks.append(dict(f, n=len(picks) + 1, repo=repo, default=default, branch=branch,
                          worktree=os.path.join(home, "improve", "worktrees", "%s-%s" % (os.path.basename(repo), f["key"]))))
    return {"date": today, "entries": picks, "skipped": [{"key": k, "why": w} for k, w in skips]}


def newest(home, day=None):
    if day:
        return os.path.join(home, "improve", day + ".json")
    paths = reports(home)
    if not paths:
        sys.exit("NONE no report in %s" % os.path.join(home, "improve"))
    return paths[-1]


def entry_of(data, n):
    for e in data["entries"]:
        if e["n"] == n:
            return e
    sys.exit("ERROR no entry %d in the %s report" % (n, data["date"]))


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def age_days(iso):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days


def compare(baseline, tokens_lines):
    after = 0
    for line in tokens_lines:
        m = PATTERN.match(line.strip())
        if m and m.group("kind") == baseline["kind"] and m.group("normalized") == baseline["normalized"]:
            after = amount(m.group("tokens"))
    return ("KEPT" if after < baseline["tokens"] else "REVERT"), after


def main(argv=None):
    ap = argparse.ArgumentParser(prog="improve.py")
    ap.add_argument("--home", default=os.path.expanduser("~/.podium"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("remotes")
    s = sub.add_parser("select")
    s.add_argument("--date", default=date.today().isoformat())
    s.add_argument("--force", action="store_true")
    b = sub.add_parser("baseline")
    b.add_argument("n", type=int)
    b.add_argument("pattern")
    k = sub.add_parser("checks")
    k.add_argument("--days", type=int, default=5)
    c = sub.add_parser("compare")
    c.add_argument("date")
    c.add_argument("n", type=int)
    r = sub.add_parser("revert")
    r.add_argument("date")
    r.add_argument("n", type=int)
    e = sub.add_parser("entry")
    e.add_argument("n", type=int, nargs="+")
    e.add_argument("--report")
    d = sub.add_parser("decide")
    d.add_argument("--report")
    d.add_argument("n", type=int)
    d.add_argument("decision", choices=["pushed", "rejected", "failed"])
    d.add_argument("detail", nargs="?", default="")
    sub.add_parser("report")
    a = ap.parse_args(argv)
    home = a.home

    if a.cmd == "remotes":
        print(" ".join("--remote " + r for r in load_config(home)["remotes"]))
    elif a.cmd == "select":
        path = os.path.join(home, "improve", a.date + ".json")
        if os.path.exists(path) and not a.force:
            sys.exit("EXISTS %s (--force replaces it)" % path)
        data = select(parse_findings(sys.stdin), load_config(home)["cap"], home, a.date)
        write(path, data)
        for p in data["entries"]:
            print("PICK %d %s ×%d %s %s %s %s from %s" % (p["n"], p["key"], p["runs"], p["kind"], p["target"],
                                                       p["repo"], p["branch"], p["default"]))
        for k in data["skipped"]:
            print("SKIP %s — %s" % (k["key"], k["why"]))
        print("REPORT %s" % path)
    elif a.cmd == "baseline":
        m = PATTERN.match(a.pattern.strip())
        if not m:
            sys.exit("ERROR not a PATTERN line: %s" % a.pattern)
        path = newest(home)
        data = read(path)
        entry_of(data, a.n)["baseline"] = {"kind": m.group("kind"), "tokens": amount(m.group("tokens")),
                                           "normalized": m.group("normalized")}
        write(path, data)
        print("BASELINE %d %s ~%d/wk" % (a.n, m.group("kind"), amount(m.group("tokens"))))
    elif a.cmd == "checks":
        for path in reports(home):
            data = read(path)
            for x in data["entries"]:
                if x.get("decision") == "pushed" and x.get("baseline") and "checked" not in x and age_days(x["at"]) >= a.days:
                    print("CHECK %s %d %s since=%s baseline=~%d/wk %s %s" % (
                        data["date"], x["n"], x["key"], x["at"], x["baseline"]["tokens"], x["baseline"]["kind"],
                        x["baseline"]["normalized"]))
    elif a.cmd == "compare":
        path = os.path.join(home, "improve", a.date + ".json")
        data = read(path)
        x = entry_of(data, a.n)
        verdict, after = compare(x["baseline"], sys.stdin)
        x["checked"] = {"verdict": verdict, "tokens": after, "at": now()}
        write(path, data)
        print("%s %s ~%d/wk → ~%d/wk sha %s" % (verdict, x["key"], x["baseline"]["tokens"], after, x["sha"]))
    elif a.cmd == "revert":
        x = entry_of(read(os.path.join(home, "improve", a.date + ".json")), a.n)
        path = newest(home)
        data = read(path)
        key = "revert-" + x["key"]
        rev = {"n": len(data["entries"]) + 1, "key": key, "kind": "revert", "target": x["target"], "runs": x["runs"],
               "title": "revert %s: no drop in tokens/week" % x["sha"], "reverts": {"key": x["key"], "sha": x["sha"]},
               "repo": x["repo"], "default": x["default"], "branch": "improve/" + key,
               "worktree": os.path.join(home, "improve", "worktrees", "%s-%s" % (os.path.basename(x["repo"]), key))}
        data["entries"].append(rev)
        write(path, data)
        print("PICK %d %s revert %s %s %s from %s" % (rev["n"], key, x["sha"], rev["repo"], rev["branch"], rev["default"]))
    elif a.cmd == "entry":
        data = read(newest(home, a.report))
        for n in a.n:
            x = entry_of(data, n)
            print("ENTRY %d %s %s %s %s %s %s%s" % (n, x["key"], x["kind"], x["repo"], x["branch"], x["default"],
                                                 x["worktree"], " DECIDED " + x["decision"] if "decision" in x else ""))
    elif a.cmd == "decide":
        path = newest(home, a.report)
        data = read(path)
        x = entry_of(data, a.n)
        x["decision"], x["at"] = a.decision, now()
        if a.decision == "pushed":
            x["sha"] = a.detail
        elif a.detail:
            x["why"] = a.detail
        write(path, data)
        print("DECIDED %d %s %s" % (a.n, x["key"], a.decision))
    elif a.cmd == "report":
        path = newest(home)
        print("REPORT %s %s" % (path[:-len(".json")] + ".md", path))


if __name__ == "__main__":
    main()
