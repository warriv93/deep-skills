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
import improve  # noqa: E402


def line(key, runs=2, status="open", kind="retro", target="deep-plan", severity="normal", saving=None):
    tail = " ~%s/wk" % saving if saving else ""
    return "FINDING %s ×%d %s %s %s %s%s — %s title" % (key, runs, status, kind, target, severity, tail, key)


class Tmp(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.tmp = os.path.realpath(self._dir.name)
        self.home = os.path.join(self.tmp, "podium-home")
        self.repo = os.path.join(self.tmp, "skills-repo")
        os.makedirs(os.path.join(self.repo, "skills", "deep-plan"))
        git = lambda *a: subprocess.run(["git", "-C", self.repo, *a], check=True, capture_output=True)
        git("init", "-q", "-b", "main")
        git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self._dir.cleanup()

    def select(self, lines, cap=5, today="2026-10-26"):
        return improve.select(improve.parse_findings(lines), cap, self.home, today,
                              resolve=lambda t: improve.resolve_target(t, podium=lambda: None) if t.startswith("repo:")
                              else (self.repo, None), branch_of=lambda r: "main")

    def run_main(self, *argv, stdin=""):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO(stdin)):
            improve.main(["--home", self.home, *argv])
        return out.getvalue().splitlines()


class ParsingFindings(Tmp):
    def test_reads_resolved_status_and_a_saving_with_a_unit(self):
        [f] = improve.parse_findings([line("big-diff", status="resolved abc123", kind="tokens", saving="12k")])
        self.assertEqual((f["status"], f["saving"], f["title"]), ("resolved abc123", 12000, "big-diff title"))

    def test_ignores_lines_that_are_not_findings(self):
        self.assertEqual(improve.parse_findings(["RECUR x ×2 — t", "", "WARN podium offline"]), [])


class SelectingFindings(Tmp):
    def test_picks_open_recurring_or_high_and_ranks_runs_times_saving_first(self):
        data = self.select([line("once", runs=1), line("once-high", runs=1, severity="high"), line("done", status="wontfix"),
                            line("twice"), line("thrice", runs=3), line("costly", kind="tokens", saving="5k")])
        self.assertEqual([e["key"] for e in data["entries"]], ["costly", "thrice", "twice", "once-high"])
        self.assertEqual([e["n"] for e in data["entries"]], [1, 2, 3, 4])
        self.assertEqual(data["entries"][0]["branch"], "improve/costly")

    def test_skips_project_repo_targets_and_findings_over_the_cap(self):
        data = self.select([line("a", runs=4), line("b", runs=3), line("c", runs=2, target="repo:api")], cap=1)
        self.assertEqual([e["key"] for e in data["entries"]], ["a"])
        self.assertEqual({s["key"]: s["why"].split(":")[0] for s in data["skipped"]},
                         {"b": "over the cap of 1", "c": "project repo api"})

    def test_skips_a_key_still_awaiting_a_decision_in_an_earlier_report(self):
        improve.write(os.path.join(self.home, "improve", "2026-10-19.json"), self.select([line("a")], today="2026-10-19"))
        data = self.select([line("a")])
        self.assertEqual(data["entries"], [])
        self.assertIn("drafted 2026-10-19", data["skipped"][0]["why"])

    def test_skips_a_key_whose_improve_branch_already_exists(self):
        subprocess.run(["git", "-C", self.repo, "branch", "improve/a"], check=True)
        self.assertIn("already exists", self.select([line("a")])["skipped"][0]["why"])


class ResolvingTargets(Tmp):
    def test_a_skill_resolves_through_its_symlink_to_the_git_toplevel(self):
        skills = os.path.join(self.tmp, "claude-skills")
        os.makedirs(skills)
        os.symlink(os.path.join(self.repo, "skills", "deep-plan"), os.path.join(skills, "deep-plan"))
        self.assertEqual(improve.resolve_target("deep-plan", skills_dir=skills), (self.repo, None))
        self.assertIsNone(improve.resolve_target("missing", skills_dir=skills)[0])

    def test_podium_resolves_from_an_editable_install_before_the_fallback(self):
        site = os.path.join(self.tmp, "site")
        os.makedirs(os.path.join(site, "podium_dashboard-0.1.dist-info"))
        with open(os.path.join(site, "podium_dashboard-0.1.dist-info", "direct_url.json"), "w") as fh:
            json.dump({"url": "file://" + self.repo, "dir_info": {"editable": True}}, fh)
        show = "Name: podium-dashboard\nLocation: %s\nFiles:\n  podium_dashboard-0.1.dist-info/direct_url.json\n" % site
        self.assertEqual(improve.podium_checkout(show, fallback=os.path.join(self.tmp, "nowhere")), self.repo)
        self.assertEqual(improve.podium_checkout("", fallback=self.repo), self.repo)


class RemeasuringTokenFixes(Tmp):
    baseline = {"kind": "reread", "tokens": 40000, "normalized": "Read <path>/SKILL.md"}

    def test_a_drop_keeps_the_fix_and_no_drop_proposes_a_revert(self):
        self.assertEqual(improve.compare(self.baseline, ["PATTERN reread ×3 ~9k/wk Read <path>/SKILL.md"]),
                         ("KEPT", 9000))
        self.assertEqual(improve.compare(self.baseline, ["PATTERN reread ×9 ~40k/wk Read <path>/SKILL.md"]),
                         ("REVERT", 40000))

    def test_a_pattern_gone_from_the_output_counts_as_a_drop_to_zero(self):
        self.assertEqual(improve.compare(self.baseline, ["TOTAL 100 sessions 2"]), ("KEPT", 0))


class TheCommandLine(Tmp):
    def test_select_baseline_decide_check_compare_and_revert_round_trip(self):
        with unittest.mock.patch.object(improve, "resolve_target", lambda t: (self.repo, None)), \
                unittest.mock.patch.object(improve, "default_branch", lambda r: "main"):
            out = self.run_main("select", "--date", "2026-10-19", stdin=line("costly", kind="tokens", saving="5k"))
        self.assertTrue(out[0].startswith("PICK 1 costly ×2 tokens deep-plan %s improve/costly from main" % self.repo))
        self.assertEqual(self.run_main("baseline", "1", "PATTERN reread ×3 ~40k/wk Read <path>"),
                         ["BASELINE 1 reread ~40000/wk"])
        self.run_main("decide", "1", "pushed", "abc1234")
        self.assertEqual(self.run_main("checks"), [])
        [check] = self.run_main("checks", "--days", "0")
        self.assertTrue(check.startswith("CHECK 2026-10-19 1 costly since="))
        self.assertEqual(self.run_main("compare", "2026-10-19", "1", stdin="PATTERN reread ×3 ~40k/wk Read <path>\n"),
                         ["REVERT costly ~40000/wk → ~40000/wk sha abc1234"])
        self.assertEqual(self.run_main("checks", "--days", "0"), [])
        self.assertEqual(self.run_main("revert", "2026-10-19", "1"),
                         ["PICK 2 revert-costly revert abc1234 %s improve/revert-costly from main" % self.repo])

    def test_select_refuses_to_replace_a_report_without_force(self):
        self.run_main("select", "--date", "2026-10-26")
        with self.assertRaises(SystemExit) as raised:
            self.run_main("select", "--date", "2026-10-26")
        self.assertIn("EXISTS", str(raised.exception))

    def test_remotes_default_to_the_configured_findings_remote_and_follow_the_config(self):
        self.assertEqual(self.run_main("remotes"), [""])
        improve.write(os.path.join(self.home, "improve.json"), {"findings": "git@example.com:f.git"})
        self.assertEqual(self.run_main("remotes"), ["--remote git@example.com:f.git"])
        improve.write(os.path.join(self.home, "improve.json"), {"remotes": ["git@example.com:x.git"], "cap": 2})
        self.assertEqual(self.run_main("remotes"), ["--remote git@example.com:x.git"])


if __name__ == "__main__":
    unittest.main()
