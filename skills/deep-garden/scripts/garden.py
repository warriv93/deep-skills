#!/usr/bin/env python3
"""The deterministic steps of /deep-garden, one line per fact.

    garden.py repos [--roots DIR...] [--also PATH...] [--findings FILE]
                                                REPO <default> <design runs> <path> / SKIP lines: this pass's repos
    garden.py hotspots <repo> [--days 90] [--top 12]
                                                HOT lines: churn over the last days × lines, highest first
    garden.py dupes <repo> [--top 20]           DUPE lines from jscpd or PMD CPD, else NODUPE <why>
    garden.py select [--date D] [--force]       stdin: each repo's REPO line, then its CANDIDATE lines →
                                                PICK/SKIP lines, writes <D>.json
    garden.py entry <n>... [--report D]         ENTRY lines, for approve/reject
    garden.py decide <n> pushed <sha>|pr <url>|failed [<why>] [--report D]
    garden.py reject <n> <why> [--report D]     records the candidate as rejected in its repo, never proposed again
    garden.py report                            the newest report's .md and .json paths

CANDIDATE <slug> <Strong|Worth-exploring|Speculative> <file,...> — <title>
A path comes last on its line, since it may hold spaces.

--name (default garden) names the report folder ~/.podium/<name>/ and the config ~/.podium/<name>.json,
{"repos": [...], "cap": 3}; --prefix the branch prefix (garden/); --rejected the rejected-candidates file,
{repo} its path and {name} its folder name (default {repo}/.deep-plan/garden-rejected.md). `--home` moves ~/.podium.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))),
                                "deep-improve", "scripts"))
from improve import default_branch, git, now, parse_findings, read, write  # noqa: E402

DEFAULT_CAP = 3
STRENGTHS = ("Strong", "Worth-exploring", "Speculative")
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
REPO = re.compile(r"^REPO (?:\S+ \d+ )?(?P<path>/.*)$")
CANDIDATE = re.compile(r"^CANDIDATE (?P<slug>\S+) (?P<strength>\S+) (?P<files>\S+) — (?P<title>.+)$")
REJECTED = re.compile(r"^- (?P<slug>\S+) \(")
SKIPPED_DIRS = {".git", "node_modules", "dist", "build", "target", "vendor", ".venv", "venv", "__pycache__", ".gradle"}
NOT_CODE = re.compile(
    r"(^|/)(\.deep-plan|node_modules|dist|build|target|vendor|generated|__snapshots__)/"
    r"|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|[^/]*\.lock|CHANGELOG[^/]*)$"
    r"|\.(md|txt|json|ya?ml|toml|csv|svg|png|jpe?g|gif|ico|snap|lock|min\.js|min\.css|map|properties|xml|sql)$", re.I)


def main_checkout(path):
    """The main checkout of the repo `path` is in (a worktree's too), or None."""
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.dirname(common) if common and os.path.basename(common) == ".git" else None


def plan_dirs(roots, depth=3):
    """Every directory holding a `.deep-plan/` at most `depth` levels under a root."""
    found = []
    for root in map(os.path.expanduser, roots):
        root = os.path.realpath(root)
        for here, dirs, _ in os.walk(root):
            if ".deep-plan" in dirs:
                found.append(here)
            level = here[len(root):].count(os.sep)
            dirs[:] = [] if level >= depth else [d for d in dirs if d not in SKIPPED_DIRS and d != ".deep-plan"]
    return found


def base_ref(repo):
    default = default_branch(repo)
    if default and git(repo, "rev-parse", "--verify", "-q", "origin/" + default):
        return default, "origin/" + default
    return default, "HEAD"


def churn(repo, ref, days):
    out = git(repo, "log", "--format=", "--name-only", "--since=%d.days" % days, ref) or ""
    return Counter(line for line in out.splitlines() if line.strip())


def design_runs(findings_lines):
    """{repo name: runs} of the open `design-*` findings the orchestrators' retros record against repo:<name>."""
    runs = {}
    for f in parse_findings(findings_lines):
        if f["key"].startswith("design-") and f["target"].startswith("repo:") and f["status"] == "open":
            name = f["target"][len("repo:"):]
            runs[name] = max(runs.get(name, 0), f["runs"])
    return runs


def repos(config_repos, roots, also, findings_lines, days=90):
    """[(path, default, design runs)] to garden and [(path, why)] skipped, the most design runs first."""
    design = design_runs(findings_lines)
    candidates = config_repos or plan_dirs(roots) + list(also)
    picked, skipped, seen = [], [], set()
    for path in map(os.path.expanduser, candidates):
        repo = main_checkout(path) if os.path.isdir(path) else None
        if not repo:
            skipped.append((path, "not a git checkout"))
            continue
        if repo in seen:
            continue
        seen.add(repo)
        default, ref = base_ref(repo)
        if not default:
            skipped.append((repo, "no default branch on origin"))
        elif not churn(repo, ref, days):
            skipped.append((repo, "no commits in the last %d days" % days))
        else:
            picked.append((repo, default, design.get(os.path.basename(repo), 0)))
    picked.sort(key=lambda r: (-r[2], r[0]))
    return picked, skipped


def line_counts(repo, ref):
    out = git(repo, "grep", "-c", "-I", "", ref, "--") or ""
    counts = {}
    for line in out.splitlines():
        path, _, n = line[len(ref) + 1:].rpartition(":")
        if n.isdigit():
            counts[path] = int(n)
    return counts


def hotspots(repo, days=90, top=12):
    """[(score, churn, lines, path)] of code files still on the base branch, churn × lines, highest first."""
    _, ref = base_ref(repo)
    changes, sizes = churn(repo, ref, days), line_counts(repo, ref)
    hot = [(n * sizes[p], n, sizes[p], p) for p, n in changes.items() if p in sizes and not NOT_CODE.search(p)]
    return sorted(hot, key=lambda h: (-h[0], h[3]))[:top]


def jscpd_dupes(repo, report_dir):
    subprocess.run(["jscpd", "--silent", "--reporters", "json", "--output", report_dir, "--min-lines", "8", "--gitignore",
                    "--ignore", "**/node_modules/**,**/dist/**,**/build/**,**/target/**,**/.deep-plan/**", repo],
                   capture_output=True, text=True, timeout=900)
    with open(os.path.join(report_dir, "jscpd-report.json")) as fh:
        dupes = json.load(fh).get("duplicates") or []
    rel = lambda f: os.path.relpath(os.path.join(repo, f["name"]) if not os.path.isabs(f["name"]) else f["name"], repo)
    return [(d.get("lines", 0), "%s:%s-%s" % (rel(d["firstFile"]), d["firstFile"]["start"], d["firstFile"]["end"]),
             "%s:%s-%s" % (rel(d["secondFile"]), d["secondFile"]["start"], d["secondFile"]["end"])) for d in dupes]


def cpd_dupes(repo):
    lang = "java" if git(repo, "ls-files", "*.java") else "kotlin" if git(repo, "ls-files", "*.kt") else None
    if not lang:
        return None
    r = subprocess.run(["pmd", "cpd", "--minimum-tokens", "100", "--dir", repo, "--language", lang, "--format", "csv"],
                       capture_output=True, text=True, timeout=900)
    out = []
    for row in r.stdout.splitlines()[1:]:
        cells = row.split(",")
        if len(cells) >= 7 and cells[0].isdigit():
            lines, spots = int(cells[0]), list(zip(cells[3::2], cells[4::2]))
            at = ["%s:%s-%d" % (os.path.relpath(f, repo), s, int(s) + lines - 1) for s, f in spots[:2]]
            out.append((lines, at[0], at[1]))
    return out


def dupes(repo, top=20):
    """(DUPE tuples, None), or ([], why none were looked for)."""
    if shutil.which("jscpd"):
        with tempfile.TemporaryDirectory() as tmp:
            found = jscpd_dupes(repo, tmp)
    elif shutil.which("pmd"):
        found = cpd_dupes(repo)
        if found is None:
            return [], "pmd cpd has no Java or Kotlin here, and jscpd is not on PATH (npm i -g jscpd)"
    else:
        return [], "no jscpd or pmd on PATH (npm i -g jscpd)"
    return sorted(found, key=lambda d: (-d[0], d[1]))[:top], None


def rejected_path(template, repo):
    return os.path.expanduser(template.replace("{repo}", repo).replace("{name}", os.path.basename(repo)))


def rejected_slugs(path):
    if not os.path.exists(path):
        return set()
    with open(path) as fh:
        return {m.group("slug") for m in map(REJECTED.match, fh) if m}


def reports(folder):
    return sorted(glob.glob(os.path.join(folder, "[0-9]*-[0-9]*-[0-9]*.json")))


def awaiting(folder):
    keys = {}
    for path in reports(folder):
        for e in read(path)["entries"]:
            if "decision" not in e:
                keys[(e["repo"], e["slug"])] = os.path.basename(path)[:-len(".json")]
    return keys


def team(repo, ref, days=90):
    authors = git(repo, "log", "--format=%ae", "--since=%d.days" % days, ref) or ""
    return len(set(authors.split())) > 1


def parse_candidates(lines):
    out, bad, repo = [], [], None
    for line in lines:
        line = line.strip()
        header = REPO.match(line)
        if header:
            repo = os.path.realpath(header.group("path"))
            continue
        if not line.startswith("CANDIDATE"):
            continue
        m = CANDIDATE.match(line)
        if repo and m and SLUG.fullmatch(m.group("slug")) and m.group("strength") in STRENGTHS:
            out.append(dict(m.groupdict(), repo=repo, files=m.group("files").split(",")))
        else:
            bad.append(line)
    return out, bad


def select(candidates, cap, folder, prefix, rejected, today, heat=None, is_team=None, branch_of=None):
    heat, is_team, branch_of = heat or hotspots, is_team or team, branch_of or base_ref
    pending, scores = awaiting(folder), {}
    picks, skips = [], []

    def rank(c):
        if c["repo"] not in scores:
            scores[c["repo"]] = {p: s for s, _, _, p in heat(c["repo"])}
        return STRENGTHS.index(c["strength"]), -sum(scores[c["repo"]].get(f, 0) for f in c["files"])

    per_repo = Counter()
    for c in sorted(candidates, key=rank):
        repo, slug, branch = c["repo"], c["slug"], prefix + c["slug"]
        reject_file = rejected_path(rejected, repo)
        why = None
        if slug in rejected_slugs(reject_file):
            why = "rejected before, in %s" % reject_file
        elif (repo, slug) in pending:
            why = "drafted %s, awaiting approve or reject" % pending[(repo, slug)]
        elif git(repo, "rev-parse", "--verify", "-q", "refs/heads/" + branch):
            why = "branch %s already exists" % branch
        elif per_repo[repo] == cap:
            why = "over the cap of %d for %s" % (cap, os.path.basename(repo))
        if why:
            skips.append({"repo": repo, "slug": slug, "why": why})
            continue
        default, ref = branch_of(repo)
        per_repo[repo] += 1
        picks.append(dict(c, n=len(picks) + 1, branch=branch, default=default, team=is_team(repo, ref),
                          worktree=os.path.join(folder, "worktrees", "%s-%s" % (re.sub(r"[^\w.-]+", "-", os.path.basename(repo)), slug))))
    return {"date": today, "entries": picks, "skipped": skips}


def newest(folder, day=None):
    if day:
        return os.path.join(folder, day + ".json")
    paths = reports(folder)
    if not paths:
        sys.exit("NONE no report in %s" % folder)
    return paths[-1]


def entry_of(data, n):
    for e in data["entries"]:
        if e["n"] == n:
            return e
    sys.exit("ERROR no entry %d in the %s report" % (n, data["date"]))


def load_config(home, name):
    path = os.path.join(home, name + ".json")
    cfg = {}
    if os.path.exists(path):
        with open(path) as fh:
            cfg = json.load(fh)
    return {"repos": cfg.get("repos") or [], "cap": int(cfg.get("cap", DEFAULT_CAP))}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="garden.py")
    ap.add_argument("--home", default=os.path.expanduser("~/.podium"))
    ap.add_argument("--name", default="garden")
    ap.add_argument("--prefix", default="garden/")
    ap.add_argument("--rejected", default="{repo}/.deep-plan/garden-rejected.md")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("repos")
    r.add_argument("--roots", nargs="*", default=["~/gitrepos"])
    r.add_argument("--also", nargs="*", default=[])
    r.add_argument("--findings")
    h = sub.add_parser("hotspots")
    h.add_argument("repo")
    h.add_argument("--days", type=int, default=90)
    h.add_argument("--top", type=int, default=12)
    d = sub.add_parser("dupes")
    d.add_argument("repo")
    d.add_argument("--top", type=int, default=20)
    s = sub.add_parser("select")
    s.add_argument("--date", default=date.today().isoformat())
    s.add_argument("--force", action="store_true")
    e = sub.add_parser("entry")
    e.add_argument("n", type=int, nargs="+")
    e.add_argument("--report")
    c = sub.add_parser("decide")
    c.add_argument("--report")
    c.add_argument("n", type=int)
    c.add_argument("decision", choices=["pushed", "pr", "failed"])
    c.add_argument("detail", nargs="?", default="")
    j = sub.add_parser("reject")
    j.add_argument("--report")
    j.add_argument("n", type=int)
    j.add_argument("why")
    sub.add_parser("report")
    a = ap.parse_args(argv)
    folder, cfg = os.path.join(a.home, a.name), load_config(a.home, a.name)

    if a.cmd == "repos":
        lines = []
        if a.findings:
            with open(a.findings) as fh:
                lines = fh.read().splitlines()
        picked, skipped = repos(cfg["repos"], a.roots, a.also, lines)
        for path, default, runs in picked:
            print("REPO %s %d %s" % (default, runs, path))
        for path, why in skipped:
            print("SKIP %s — %s" % (path, why))
    elif a.cmd == "hotspots":
        for score, n, lines, path in hotspots(os.path.realpath(a.repo), a.days, a.top):
            print("HOT %d ×%d %dL %s" % (score, n, lines, path))
    elif a.cmd == "dupes":
        found, why = dupes(os.path.realpath(a.repo), a.top)
        for lines, first, second in found:
            print("DUPE %dL %s %s" % (lines, first, second))
        if why:
            print("NODUPE %s" % why)
    elif a.cmd == "select":
        path = os.path.join(folder, a.date + ".json")
        if os.path.exists(path) and not a.force:
            sys.exit("EXISTS %s (--force replaces it)" % path)
        candidates, bad = parse_candidates(sys.stdin)
        data = select(candidates, cfg["cap"], folder, a.prefix, a.rejected, a.date)
        write(path, data)
        for p in data["entries"]:
            print("PICK %d %s %s %s from %s %s in %s" % (p["n"], p["slug"], p["strength"], p["branch"], p["default"],
                                                       "team" if p["team"] else "solo", p["repo"]))
        for k in data["skipped"]:
            print("SKIP %s — %s, in %s" % (k["slug"], k["why"], k["repo"]))
        for line in bad:
            print("BAD %s" % line)
        print("REPORT %s" % path)
    elif a.cmd == "entry":
        data = read(newest(folder, a.report))
        for n in a.n:
            x = entry_of(data, n)
            print("ENTRY %d %s %s %s %s %s%s in %s" % (n, x["slug"], x["branch"], x["default"], x["worktree"],
                                                    "team" if x["team"] else "solo",
                                                    " DECIDED " + x["decision"] if "decision" in x else "", x["repo"]))
    elif a.cmd in ("decide", "reject"):
        path = newest(folder, a.report)
        data = read(path)
        x = entry_of(data, a.n)
        x["decision"], x["at"] = ("rejected" if a.cmd == "reject" else a.decision), now()
        if a.cmd == "reject":
            x["why"] = a.why
            target = rejected_path(a.rejected, x["repo"])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            fresh = not os.path.exists(target)
            with open(target, "a") as fh:
                if fresh:
                    fh.write("# Garden candidates rejected\n\nThe codebase-gardening pass never proposes these again.\n\n")
                fh.write("- %s (%s): %s — %s\n" % (x["slug"], data["date"], a.why, ", ".join(x["files"])))
            print("REJECTED %d %s → %s" % (a.n, x["slug"], target))
        else:
            x["sha" if a.decision == "pushed" else "url" if a.decision == "pr" else "why"] = a.detail
        write(path, data)
        print("DECIDED %d %s %s" % (a.n, x["slug"], x["decision"]))
    elif a.cmd == "report":
        path = newest(folder)
        print("REPORT %s %s" % (path[:-len(".json")] + ".md", path))


if __name__ == "__main__":
    main()
