import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import garden  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


class Tmp(unittest.TestCase):
    """repos/app: a clone of a bare origin on main, with a .deep-plan/ and a worktree beside it."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp = os.path.realpath(self._dir.name)
        env = unittest.mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        self.home = os.path.join(self.tmp, "home")
        self.root = os.path.join(self.tmp, "repos")
        origin, self.repo = os.path.join(self.tmp, "app.git"), os.path.join(self.root, "app")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", origin)
        self.git(self.tmp, "clone", "-q", origin, self.repo)
        self.commit("src/big.py", 40, "init")
        self.git(self.repo, "push", "-q", "origin", "main")
        self.git(self.repo, "remote", "set-head", "origin", "main")
        os.makedirs(os.path.join(self.repo, ".deep-plan"))

    def git(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, path, lines, message, push=False):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "a") as fh:
            fh.write("".join("line %s %d\n" % (message, i) for i in range(lines)))
        self.git(self.repo, "add", path)
        self.git(self.repo, "commit", "-q", "-m", message)
        if push:
            self.git(self.repo, "push", "-q", "origin", "main")

    def run_main(self, *argv, stdin=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(stdin)):
            garden.main(["--home", self.home, *argv])
        return out.getvalue().splitlines()


class Repos(Tmp):
    def test_finds_run_repos_through_their_worktrees_once_and_skips_dormant_or_originless_ones(self):
        tree = os.path.join(self.tmp, "repos", ".wt", "app-feature")
        self.git(self.repo, "worktree", "add", "-q", "-b", "feature", tree)
        os.makedirs(os.path.join(tree, ".deep-plan"), exist_ok=True)
        lone = os.path.join(self.root, "lone")
        os.makedirs(os.path.join(lone, ".deep-plan"))
        self.git(lone, "init", "-q", "-b", "main")
        picked, skipped = garden.repos([], [self.root], [], [])
        self.assertEqual(picked, [(self.repo, "main", 0)])
        self.assertEqual(skipped, [(lone, "no default branch on origin")])
        old, old_origin = os.path.join(self.root, "old"), os.path.join(self.tmp, "old.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", old_origin)
        self.git(self.tmp, "clone", "-q", old_origin, old)
        with unittest.mock.patch.dict(os.environ, {"GIT_COMMITTER_DATE": "2020-01-01T00:00:00", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00"}):
            self.git(old, "commit", "-q", "--allow-empty", "-m", "old")
        self.git(old, "push", "-q", "origin", "main")
        self.git(old, "remote", "set-head", "origin", "main")
        self.assertEqual(garden.repos([old], [], [], [])[1], [(old, "no commits in the last 90 days")])

    def test_config_repos_replace_discovery_and_recurring_design_findings_go_first(self):
        findings = ["FINDING design-app ×3 open design repo:app normal — the quality gate found design problems in app",
                    "FINDING design-gone ×5 wontfix design repo:gone normal — t"]
        self.assertEqual(self.run_main("repos", "--roots", self.tmp, "--findings", self.write("f.txt", findings)),
                         ["REPO main 3 %s" % self.repo])
        with open(os.path.join(self.home, "garden.json"), "w") as fh:
            json.dump({"repos": [os.path.join(self.tmp, "nowhere")]}, fh)
        self.assertEqual(self.run_main("repos"), ["SKIP %s — not a git checkout" % os.path.join(self.tmp, "nowhere")])

    def write(self, name, lines):
        os.makedirs(self.home, exist_ok=True)
        path = os.path.join(self.home, name)
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        return path


class Hotspots(Tmp):
    def test_ranks_code_on_the_base_branch_by_churn_times_lines_and_leaves_out_docs_locks_and_deleted_files(self):
        for i in range(3):
            self.commit("src/small.py", 5, "small%d" % i)
        self.commit("src/big.py", 10, "big")
        self.commit("package-lock.json", 500, "lock")
        self.commit("README.md", 500, "docs")
        self.commit("src/gone.py", 5, "gone")
        self.git(self.repo, "rm", "-q", "src/gone.py")
        self.git(self.repo, "commit", "-q", "-m", "rm")
        self.git(self.repo, "push", "-q", "origin", "main")
        self.commit("src/local.py", 100, "unpushed")
        self.assertEqual(self.run_main("hotspots", self.repo), ["HOT 100 ×2 50L src/big.py", "HOT 45 ×3 15L src/small.py"])


class Dupes(Tmp):
    def fake(self, name, script):
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir, exist_ok=True)
        with open(os.path.join(bin_dir, name), "w") as fh:
            fh.write("#!/bin/sh\n" + script)
        os.chmod(os.path.join(bin_dir, name), 0o755)
        return unittest.mock.patch.dict(os.environ, {"PATH": bin_dir})

    def test_reads_jscpds_json_report_largest_first(self):
        report = {"duplicates": [
            {"lines": 9, "firstFile": {"name": "src/a.ts", "start": 1, "end": 9}, "secondFile": {"name": "src/b.ts", "start": 4, "end": 12}},
            {"lines": 30, "firstFile": {"name": self.repo + "/src/c.ts", "start": 10, "end": 39},
             "secondFile": {"name": "src/d.ts", "start": 1, "end": 30}}]}
        script = 'while [ "$1" != "--output" ]; do shift; done; echo \'%s\' > "$2/jscpd-report.json"\n' % json.dumps(report)
        with self.fake("jscpd", script):
            self.assertEqual(self.run_main("dupes", self.repo),
                             ["DUPE 30L src/c.ts:10-39 src/d.ts:1-30", "DUPE 9L src/a.ts:1-9 src/b.ts:4-12"])

    def test_says_why_without_a_duplication_tool(self):
        with unittest.mock.patch.dict(os.environ, {"PATH": os.path.join(self.tmp, "empty")}):
            self.assertEqual(self.run_main("dupes", self.repo), ["NODUPE no jscpd or pmd on PATH (npm i -g jscpd)"])


def cand(slug, strength="Strong", files="src/big.py"):
    return "CANDIDATE %s %s %s — deepen %s" % (slug, strength, files, slug)


class Selecting(Tmp):
    def lines(self, *specs):
        return "REPO main 0 %s\n" % self.repo + "\n".join(cand(*s) for s in specs) + "\n"

    def test_ranks_by_strength_then_hotspot_heat_caps_per_repo_and_reports_bad_lines(self):
        self.commit("src/big.py", 1, "again", push=True)
        out = self.run_main("select", "--date", "2026-11-07", stdin=self.lines(
            ("cold", "Strong", "src/none.py"), ("hot", "Strong", "src/big.py"), ("maybe", "Speculative", "src/big.py"),
            ("worth", "Worth-exploring", "src/big.py")) + "CANDIDATE nonsense\n")
        report = os.path.join(self.home, "garden", "2026-11-07.json")
        self.assertEqual(out, ["PICK 1 hot Strong garden/hot from main solo in %s" % self.repo,
                               "PICK 2 cold Strong garden/cold from main solo in %s" % self.repo,
                               "PICK 3 worth Worth-exploring garden/worth from main solo in %s" % self.repo,
                               "SKIP maybe — over the cap of 3 for app, in %s" % self.repo,
                               "BAD CANDIDATE nonsense", "REPORT %s" % report])
        self.assertEqual(garden.read(report)["entries"][0]["worktree"],
                         os.path.join(self.home, "garden", "worktrees", "app-hot"))
        with self.assertRaisesRegex(SystemExit, "^EXISTS"):
            self.run_main("select", "--date", "2026-11-07", stdin="")

    def test_skips_rejected_awaiting_and_existing_branches(self):
        self.run_main("select", "--date", "2026-10-07", stdin=self.lines(("waiting",)))
        self.git(self.repo, "branch", "garden/branched")
        with open(os.path.join(self.repo, ".deep-plan", "garden-rejected.md"), "w") as fh:
            fh.write("# Garden candidates rejected\n\n- nope (2026-09-07): we like it — src/big.py\n")
        out = self.run_main("select", "--date", "2026-11-07", stdin=self.lines(("waiting",), ("branched",), ("nope",)))
        self.assertEqual(out[:3], [
            "SKIP waiting — drafted 2026-10-07, awaiting approve or reject, in %s" % self.repo,
            "SKIP branched — branch garden/branched already exists, in %s" % self.repo,
            "SKIP nope — rejected before, in %s, in %s" % (os.path.join(self.repo, ".deep-plan", "garden-rejected.md"), self.repo)])

    def test_a_second_author_makes_a_team_repo_and_the_prefix_names_the_branch(self):
        with unittest.mock.patch.dict(os.environ, {"GIT_AUTHOR_EMAIL": "other@t"}):
            self.commit("src/big.py", 1, "theirs", push=True)
        out = self.run_main("--prefix", "simon/garden-", "select", stdin=self.lines(("one",)))
        self.assertEqual(out[0], "PICK 1 one Strong simon/garden-one from main team in %s" % self.repo)


class Deciding(Tmp):
    def setUp(self):
        super().setUp()
        self.run_main("select", "--date", "2026-11-07",
                      stdin="REPO %s\n%s\n%s\n" % (self.repo, cand("one"), cand("two", files="src/big.py,src/x.py")))

    def test_reject_records_the_slug_in_the_repos_rejected_file_so_select_skips_it(self):
        rejected = os.path.join(self.repo, ".deep-plan", "garden-rejected.md")
        self.assertEqual(self.run_main("reject", "2", "the split is on purpose"),
                         ["REJECTED 2 two → %s" % rejected, "DECIDED 2 two rejected"])
        with open(rejected) as fh:
            self.assertTrue(fh.read().endswith("- two (2026-11-07): the split is on purpose — src/big.py, src/x.py\n"))
        self.assertEqual(garden.rejected_slugs(rejected), {"two"})
        self.assertEqual(self.run_main("entry", "1", "2"), [
            "ENTRY 1 one garden/one main %s solo in %s" % (os.path.join(self.home, "garden", "worktrees", "app-one"), self.repo),
            "ENTRY 2 two garden/two main %s solo DECIDED rejected in %s" % (os.path.join(self.home, "garden", "worktrees", "app-two"), self.repo)])

    def test_a_rejected_file_template_moves_it_out_of_the_repo(self):
        out = self.run_main("--rejected", os.path.join(self.tmp, "rej", "{name}.md"), "reject", "1", "no")
        self.assertEqual(out[0], "REJECTED 1 one → %s" % os.path.join(self.tmp, "rej", "app.md"))

    def test_decide_records_a_push_or_a_pr(self):
        self.assertEqual(self.run_main("decide", "1", "pushed", "abc1234"), ["DECIDED 1 one pushed"])
        self.run_main("decide", "2", "pr", "https://example/pr/1")
        entries = garden.read(os.path.join(self.home, "garden", "2026-11-07.json"))["entries"]
        self.assertEqual((entries[0]["sha"], entries[1]["url"]), ("abc1234", "https://example/pr/1"))
        self.assertEqual(self.run_main("report"), ["REPORT %s %s" % (
            os.path.join(self.home, "garden", "2026-11-07.md"), os.path.join(self.home, "garden", "2026-11-07.json"))])


if __name__ == "__main__":
    unittest.main()
