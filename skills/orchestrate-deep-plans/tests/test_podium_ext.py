"""Tests for podium_ext.py's verbs, run through the `podium` command in this process: merge, brief, breakdown, handoff,
launch, land, peek, turn (base branches, landings, requests, sync's pull line) and the Podium's prompts.

Each test builds a run in a temp dir: a repo with a bare origin, its .deep-plan/podium/podium.json naming this
extension, and fake `gh` and `paseo` binaries on PATH.

    PYTHONPATH=<podium-dashboard checkout> python3 -m unittest discover -s tests
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import types
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import podium_dashboard
from podium_dashboard import cli, extension, human
from podium_dashboard.state import Podium

try:
    import podium_dashboard.sync  # noqa: F401
except ImportError:  # a podium-dashboard from before `podium sync`: turn needs only its pull
    stub = types.ModuleType("podium_dashboard.sync")
    stub.enabled, stub.save, stub.pull = lambda p: False, lambda p, message: "OFF", lambda p: "OFF"
    stub.is_major = lambda p, event: False
    sys.modules["podium_dashboard.sync"] = podium_dashboard.sync = stub

EXT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "podium_ext.py")
TOOL = os.path.dirname(os.path.dirname(os.path.abspath(podium_dashboard.__file__)))
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def short(cmd):
    return hashlib.sha256(cmd.encode()).hexdigest()[:12]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def ago(minutes):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def commit(cwd, name, message, text="x"):
    with open(os.path.join(cwd, name), "w") as f:
        f.write(text)
    git(cwd, "add", name)
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


class Run(unittest.TestCase):
    """The repo `core/` on master (origin.git its origin), its run in core/.deep-plan, and milestone M1 on
    branch feat, checked out in the worktree feat/."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "bin"))
        env = unittest.mock.patch.dict(os.environ, {**GIT_ENV, "PODIUM_EXTENSION_FILE": os.path.join(self.tmp, "podium_ext.py"), "PATH": os.path.join(self.tmp, "bin") + os.pathsep + os.environ["PATH"],
                                                    "PODIUM_PASEO": self.fake("paseo", "echo 'no paseo here' >&2; exit 1\n"),
                                                    "PODIUM_TOOL": self.fake("podium-tool", "")})
        env.start()
        self.addCleanup(env.stop)
        for k in ("PODIUM_DIR", "PODIUM_STORY", "PODIUM_MILESTONE", "PODIUM_ME", "ASANA_TOKEN"):
            os.environ.pop(k, None)
        hours = unittest.mock.patch.object(human, "HUMAN_FILE", os.path.join(self.tmp, "human.json"))
        hours.start()
        self.addCleanup(hours.stop)
        self.fake("gh", "echo 'no gh here' >&2; exit 1\n")
        self.origin, self.main = os.path.join(self.tmp, "origin.git"), os.path.join(self.tmp, "core")
        git(self.tmp, "init", "-q", "--bare", "-b", "master", self.origin)
        git(self.tmp, "clone", "-q", self.origin, self.main)
        commit(self.main, "a.txt", "init")
        git(self.main, "push", "-q", "origin", "master")
        git(self.main, "remote", "set-head", "origin", "master")
        self.run_dir = os.path.join(self.main, ".deep-plan")
        with open(os.path.join(self.main, ".git", "info", "exclude"), "a") as f:
            f.write("/.deep-plan/\n")
        self.feature = os.path.join(self.tmp, "feat")
        git(self.main, "worktree", "add", "-q", "-b", "feat", self.feature, "master")
        self.data = {
            "project": {"title": "T"}, "active": {"epic": "e", "milestone": "M1"}, "needsYou": None, "dispatcher": "agent",
            "orchestrator": {"name": "orchestrate-deep-plans", "command": "/orchestrate-deep-plans", "extension": EXT},
            "assumptions": [{"question": "q0", "choice": "c", "why": "w", "status": "open"},
                            {"question": "q1", "choice": "c", "why": "w", "status": "confirmed"}],
            "epics": [{"id": "e", "title": "E", "milestones": [{
                "id": "M1", "title": "Feat", "status": "working", "phase": "build", "branch": "feat", "pr": None,
                "quality": {"contract": []},
                "stories": [{"id": "S1", "title": "One", "status": "todo", "deps": [], "model": "opus", "attempts": 0},
                            {"id": "S2", "title": "Two", "status": "todo", "deps": ["S1"], "model": "sonnet", "attempts": 0}]}]}]}
        self.write()

    def write(self):
        os.makedirs(os.path.join(self.run_dir, "podium"), exist_ok=True)
        with open(os.path.join(self.run_dir, "podium", "podium.json"), "w") as f:
            json.dump(self.data, f)

    def call(self, *args):
        """(exit code, stdout and stderr) of `podium --dir <run> <args>`."""
        out, code = io.StringIO(), 0
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                cli.main(["--dir", self.run_dir, *args])
            except SystemExit as e:
                if isinstance(e.code, str):
                    print(e.code, file=sys.stderr)
                code = 1 if isinstance(e.code, str) else e.code or 0
        return code, out.getvalue()

    def podium(self, *args, code=0):
        got, out = self.call(*args)
        self.assertEqual(got, code, out)
        return out

    def ext(self):
        module, why = extension.load(Podium(self.run_dir))
        self.assertIsNone(why)
        return module

    def state(self):
        with open(os.path.join(self.run_dir, "podium", "podium.json")) as f:
            return json.load(f)

    def milestone(self):
        return self.state()["epics"][0]["milestones"][0]

    def events(self):
        path = os.path.join(self.run_dir, "podium", "events.jsonl")
        with open(path) if os.path.exists(path) else io.StringIO() as f:
            return [json.loads(line) for line in f]

    def fake(self, name, script):
        path = os.path.join(self.tmp, "bin", name)
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + textwrap.dedent(script))
        os.chmod(path, 0o755)
        return path

    def other_clone(self):
        other = os.path.join(self.tmp, "other")
        git(self.tmp, "clone", "-q", self.origin, other)
        return other

    def story_branch(self, sid, start="feat"):
        tree = os.path.join(self.tmp, sid.lower())
        git(self.main, "worktree", "add", "-q", "-b", f"story/{sid}", tree, start)
        return tree


class Merge(Run):
    def test_a_merge_keeps_the_writes_other_commands_made_while_its_contract_ran(self):
        started, go = os.path.join(self.tmp, "started"), os.path.join(self.tmp, "go")
        self.data["epics"][0]["milestones"][0]["quality"]["contract"] = [
            {"cmd": f"touch {started}; while [ ! -f {go} ]; do sleep 0.1; done"}]
        self.write()
        commit(self.story_branch("S1"), "s.txt", "feat: one\n\nStory: S1")
        result = []
        merge = threading.Thread(target=lambda: result.append(self.call("merge", "S1")))
        merge.start()
        self.addCleanup(lambda: open(go, "w").close() or merge.join(60))
        deadline = time.time() + 30
        while not os.path.exists(started) and time.time() < deadline:
            time.sleep(0.05)
        core = lambda *args: subprocess.run([sys.executable, "-m", "podium_dashboard", "--dir", self.run_dir, *args], check=True,
                                            capture_output=True, env={**os.environ, "PYTHONPATH": TOOL})
        core("set", "S2", "title=Renamed meanwhile")
        core("assume", "q?", "c", "w")
        open(go, "w").close()
        merge.join(60)
        code, out = result[0]
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("MERGED S1 1 commits"), out)
        m = self.milestone()
        self.assertEqual([(s["status"], s["title"]) for s in m["stories"]], [("done", "One"), ("todo", "Renamed meanwhile")])
        self.assertIs(m["quality"]["contract"][0]["ok"], True)
        self.assertEqual(self.state()["assumptions"][-1]["question"], "q?")
        self.assertTrue(os.path.exists(os.path.join(self.feature, "s.txt")))  # merged where feat is checked out

    def test_the_merge_that_completes_a_wave_marks_its_event(self):
        self.data["epics"][0]["milestones"][0]["stories"][1]["deps"] = []
        self.write()
        for sid in ("S1", "S2"):
            commit(self.story_branch(sid), f"{sid}.txt", f"feat: {sid}\n\nStory: {sid}")
            self.podium("set", sid, "status=working")
        self.podium("merge", "S1")
        self.podium("merge", "S2")
        self.assertEqual([(e["story"], e.get("wave")) for e in self.events() if e["type"] == "merged"], [("S1", None), ("S2", True)])

    def test_a_conflict_aborts_the_merge_and_counts_it(self):
        commit(self.story_branch("S1"), "a.txt", "feat: one", text="story")
        commit(self.feature, "a.txt", "meanwhile", text="milestone")
        self.assertEqual(self.podium("merge", "S1", code=2).strip(), "CONFLICT S1 1")
        self.assertEqual(self.milestone()["stories"][0]["conflicts"], 1)
        self.assertEqual(git(self.feature, "status", "--porcelain"), "")

    def test_a_red_contract_undoes_the_merge(self):
        self.data["epics"][0]["milestones"][0]["quality"]["contract"] = [{"cmd": "echo broken; exit 1"}]
        self.write()
        before = git(self.feature, "rev-parse", "HEAD")
        commit(self.story_branch("S1"), "s.txt", "feat: one")
        out = self.podium("merge", "S1", code=3)
        self.assertEqual(out.splitlines()[:3], ["RED S1 echo broken; exit 1", "$ echo broken; exit 1", "broken"])
        self.assertEqual(git(self.feature, "rev-parse", "HEAD"), before)
        self.assertEqual(self.milestone()["stories"][0]["status"], "todo")

    def test_an_unsynced_run_runs_its_contract_without_approval(self):
        marker = os.path.join(self.tmp, "ran")
        self.data["epics"][0]["milestones"][0]["quality"]["contract"] = [{"cmd": f"echo >> {marker}"}]
        self.write()
        commit(self.story_branch("S1"), "s.txt", "feat: one")
        self.assertTrue(self.podium("merge", "S1").startswith("MERGED S1 1 commits"))
        self.assertTrue(os.path.exists(marker))
        self.assertEqual(self.podium("approve"), "")


class MergeQueue(Run):
    """S1, S2 and S3 working, each with a committed story branch; S4 todo after S3. The contract fails once S2.txt is in."""

    def setUp(self):
        super().setUp()
        m = self.data["epics"][0]["milestones"][0]
        m["quality"]["contract"] = [{"cmd": "test ! -f S2.txt"}]
        m["stories"] = [{"id": sid, "title": sid, "status": "working", "deps": [], "attempts": 1} for sid in ("S1", "S2", "S3")]
        m["stories"].append({"id": "S4", "title": "S4", "status": "todo", "deps": ["S3"], "attempts": 0})
        self.write()
        for sid in ("S1", "S2", "S3"):
            commit(self.story_branch(sid), f"{sid}.txt", f"feat: {sid}\n\nStory: {sid}")

    def statuses(self):
        return [s["status"] for s in self.milestone()["stories"]]

    def test_stops_at_the_first_red_and_names_the_ids_it_never_reached(self):
        out = self.podium("merge", "S1", "S2", "S3", "--land", code=3)
        self.assertEqual(out.splitlines(), ["MERGED S1 1 commits; ready: -", "LANDED S1",
                                            "RED S2 test ! -f S2.txt", "$ test ! -f S2.txt",
                                            "STOPPED S2 RED", "PENDING S3"])
        self.assertEqual(self.statuses(), ["done", "working", "working", "todo"])
        self.assertFalse(os.path.exists(os.path.join(self.feature, "S3.txt")))

    def test_lands_each_merged_story_before_the_next_and_passes_next_on(self):
        self.data["epics"][0]["milestones"][0].update(buildAll=True, quality={"contract": []})
        self.write()
        out = self.podium("merge", "S1", "M1/S1", "S2", "S3", "--land", "--next")
        prompt = os.path.join(self.run_dir, "podium", "stories", "M1", "S4.prompt")
        self.assertEqual(out.splitlines(), [
            "MERGED S1 1 commits; ready: -", "LANDED S1; wave waits on S2 S3",
            "MERGED S2 1 commits; ready: -", "LANDED S2; wave waits on S3",
            "MERGED S3 1 commits; ready: S4", "LANDED S3; launched S4", f"PROMPT {prompt} model=sonnet"])
        self.assertEqual(self.statuses(), ["done", "done", "done", "working"])

    def test_an_unknown_story_stops_the_queue_with_why(self):
        out = self.podium("merge", "S1", "S9", "S3", "--land", code=1)
        self.assertEqual(out.splitlines(), ["MERGED S1 1 commits; ready: -", "LANDED S1",
                                            "STOPPED S9 ERROR: no story 'S9' in M1", "PENDING S3"])
        self.assertEqual(self.statuses(), ["done", "working", "working", "todo"])

    def test_a_single_story_without_land_merges_as_before(self):
        self.assertEqual(self.podium("merge", "S1"), "MERGED S1 1 commits; ready: -\n")
        self.assertEqual(self.podium("merge", "S2", code=3), "RED S2 test ! -f S2.txt\n$ test ! -f S2.txt\n")
        self.assertEqual(self.statuses(), ["done", "working", "working", "todo"])

    def test_next_without_land_merges_nothing(self):
        self.assertEqual(self.podium("merge", "S1", "--next", code=1),
                         "merge <story>... | <milestone>/<story>... [--land [--next]] [--force]\n")
        self.assertEqual(self.statuses(), ["working", "working", "working", "todo"])

    def test_peek_shows_the_gates_and_commit_the_merge_recorded(self):
        sha = git(self.main, "rev-parse", "story/S1")
        self.podium("merge", "S1")
        self.assertEqual(self.milestone()["quality"]["contract"][0]["story"], "S1")
        self.assertRegex(self.podium("peek", "S1"), rf"^M1/S1 done \d+s ago · progress - · gates contract✓ · agent - · committed {sha[:7]}\n$")


class Contracts(Run):
    """A run that syncs to origin, M1 owned by alice, whose contract appends to the file `ran`; S1 waits to merge."""

    def setUp(self):
        super().setUp()
        os.environ["PODIUM_ME"] = "alice"
        self.marker = os.path.join(self.tmp, "ran")
        self.cmd = f"echo ran >> {self.marker}"
        m = self.data["epics"][0]["milestones"][0]
        m["owner"], m["quality"]["contract"] = "alice", [{"cmd": self.cmd}]
        self.data["sync"] = {"enabled": True, "remote": "origin", "ref": "refs/heads/podium-run/core"}
        self.write()
        self.podium("sync", "save", "start")
        commit(self.story_branch("S1"), "s.txt", "feat: one\n\nStory: S1")

    def refused_merge(self, cmd):
        before = git(self.feature, "rev-parse", "HEAD")
        self.assertEqual(self.podium("merge", "S1", code=1), f"CONTRACT-CHANGED {short(cmd)} core: {ascii(cmd)}\n")
        self.assertFalse(os.path.exists(self.marker))
        self.assertEqual(git(self.feature, "rev-parse", "HEAD"), before)
        self.assertEqual(self.milestone()["stories"][0]["status"], "todo")
        self.assertNotIn("merged", [e["type"] for e in self.events()])

    def test_merge_runs_no_command_this_machine_has_not_approved(self):
        self.refused_merge(self.cmd)

    def test_a_changed_contract_stops_a_merge_queue(self):
        out = self.podium("merge", "S1", "S2", "--land", code=1)
        self.assertEqual(out.splitlines(), [f"CONTRACT-CHANGED {short(self.cmd)} core: {ascii(self.cmd)}",
                                            "STOPPED S1 CONTRACT-CHANGED", "PENDING S2"])
        self.assertFalse(os.path.exists(self.marker))
        self.assertEqual([s["status"] for s in self.milestone()["stories"]], ["todo", "todo"])

    def test_merge_runs_the_command_once_approved(self):
        self.assertEqual(self.podium("approve"), f"PENDING {short(self.cmd)} core: {ascii(self.cmd)}\n")
        self.assertEqual(self.podium("approve", "all"), "APPROVED 1\n")
        self.assertEqual(self.podium("approve"), "")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "approved.json")))
        self.assertTrue(self.podium("merge", "S1").startswith("MERGED S1 1 commits"))
        with open(self.marker) as f:
            self.assertEqual(f.read(), "ran\n")

    def test_a_pulled_change_to_an_approved_command_stops_the_merge_again(self):
        self.podium("approve", "all")
        changed = f"echo changed >> {self.marker}"
        there = os.path.join(self.other_clone(), ".deep-plan")
        os.makedirs(there)
        for args in (("sync", "on", "--ref", "refs/heads/podium-run/core"), ("sync", "pull"),
                     ("set", "milestone:M1", "quality.contract=" + json.dumps([{"cmd": changed}])),
                     ("sync", "save", "contract")):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(["--dir", there, *args])
        self.assertTrue(self.podium("sync", "pull").startswith("PULLED"))
        self.refused_merge(changed)
        self.assertEqual(self.podium("approve"), f"PENDING {short(changed)} core: {ascii(changed)}\n")

    def contract(self, *cmds):
        self.podium("set", "milestone:M1", "quality.contract=" + json.dumps([{"cmd": c} for c in cmds]))

    def test_approves_only_the_commands_it_names(self):
        other = "echo other"
        self.contract(self.cmd, other)
        self.assertEqual(self.podium("approve", short(other)[:8]), "APPROVED 1\n")
        self.assertEqual(self.podium("approve"), f"PENDING {short(self.cmd)} core: {ascii(self.cmd)}\n")
        self.refused_merge(self.cmd)

    def test_an_ambiguous_digest_approves_nothing(self):
        self.contract("echo 32685", "echo 75593")
        self.assertEqual(self.podium("approve", "76aa8c5f", code=1),
                         "ambiguous digest 76aa8c5f: 2 pending commands have it\n")
        self.assertEqual(len(self.podium("approve").splitlines()), 2)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "approved.json")))

    def test_shows_a_command_with_control_characters_escaped(self):
        sneaky = "echo ok\rrm -rf x"
        self.contract(sneaky)
        self.assertEqual(self.podium("approve"), f"PENDING {short(sneaky)} core: 'echo ok\\rrm -rf x'\n")
        self.assertEqual(self.podium("merge", "S1", code=1), f"CONTRACT-CHANGED {short(sneaky)} core: 'echo ok\\rrm -rf x'\n")

    def test_an_unknown_or_short_digest_approves_nothing(self):
        self.assertEqual(self.podium("approve", short(self.cmd), "0123456789ab", code=1),
                         "unknown digest 0123456789ab: no pending command has it\n")
        seven = short(self.cmd)[:7]
        self.assertEqual(self.podium("approve", seven, code=1), f"not a digest: {seven} (8 or more hex chars)\n")
        self.assertEqual(self.podium("approve"), f"PENDING {short(self.cmd)} core: {ascii(self.cmd)}\n")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "approved.json")))


class Brief(Run):
    def test_prints_the_brief_and_only_the_sections_it_references(self):
        with open(os.path.join(self.run_dir, "architecture.md"), "w") as f:
            f.write("# Arch\n\n## Invite service\nservice text\n### Detail\ndetail text\n\n## Email queue\nqueue text\n\n"
                    "## Unrelated\nnope\n```\n## Not a heading\n```\n\n## `InviteToken`\ntoken text\n## Rate limits\n20 an hour\n")
        os.makedirs(os.path.join(self.run_dir, "spec"))
        with open(os.path.join(self.run_dir, "spec", "tasks.md"), "w") as f:
            f.write("# Tasks\n\n## S1 · One\n- [ ] T001 [core] do it\n\n## S10 · Ten\n- [ ] T010 other\n")
        os.makedirs(os.path.join(self.run_dir, "podium", "stories", "M1"))
        with open(os.path.join(self.run_dir, "podium", "stories", "M1", "S1.md"), "w") as f:
            f.write("# S1 · One\n## Context\n- [service](../../../architecture.md#invite-service)\n"
                    "- architecture.md § Email queue\n- uses `InviteToken`\n- architecture.md#gone\n"
                    "- see architecture.md#Rate limits for the cap\n")
        out = self.podium("brief", "S1")
        self.assertTrue(out.startswith("# S1 · One"))
        for want in ("=== architecture.md § Invite service", "detail text", "=== architecture.md § Email queue",
                     "=== architecture.md § `InviteToken`", "=== spec/tasks.md § S1 · One", "T001", "MISSING architecture.md#gone"):
            self.assertIn(want, out)
        self.assertIn("=== architecture.md § Rate limits", out)
        for unwanted in ("nope", "Not a heading", "T010", "§ Detail"):
            self.assertNotIn(unwanted, out)


TASKS = """\
# Tasks: Invites

**Input**: `specs/001-invites/`

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [ ] T001 Add the module in src/invites/__init__.py

## Phase 2: Foundational

- [ ] T002 [P] Define `Invite` in `src/invites/model.py`

## Phase 3: User Story 1 - Send an invite (Priority: P1) 🎯 MVP

**Goal**: An owner sends an invite by email. Nothing reads it yet.

**Independent Test**: one invite arrives.

**Critical**: yes: the token is a secret.

**Context**: `architecture.md#Invite service`

### Tests for User Story 1

- [ ] T010 [P] [US1] Write the failing invite test in tests/test_invite.py
- [ ] T011 [US1] Implement the invite service in `src/invites/service.py`,
      reusing src/invites/model.py

## Phase 4: User Story 2 - Accept an invite (Priority: P2)

**Goal**: The invitee accepts before its date, in the inviter's time zone.

**Context**: `architecture.md#Invite service`, `architecture.md#Accept flow`

- [ ] T020 [US2] Write the failing accept test, then accept in src/invites/service.py
- [ ] T021 [US2] Store the acceptance in `src/invites/store.py`

## Phase 5: User Story 3 - List invites (Priority: P3)

- [ ] T030 [P] [US3] Show the list in src/web/invites.tsx, read from src/invites/store.py

## Phase 6: Polish

- [ ] T040 Document it in docs/invites.md

## Dependencies & Execution Order

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 and US9 (needs its service)
- US3 needs nothing from US1–US2; it can start after Foundational - may integrate with US2
"""


class Breakdown(Run):
    """deep-plan's speckit tasks.md in the repo's specs/001-invites/, its spec.md beside it, architecture.md in the run."""

    def setUp(self):
        super().setUp()
        self.data["epics"][0]["milestones"][0]["stories"] = []
        self.write()
        spec = os.path.join(self.main, "specs", "001-invites")
        os.makedirs(spec)
        self.tasks = os.path.join(spec, "tasks.md")
        self.tasks_md(TASKS)
        with open(os.path.join(spec, "spec.md"), "w") as f:
            f.write("# Spec\n\n### User Story 1 - Send an invite (Priority: P1)\nsend text\n\n"
                    "### User Story 2 - Accept an invite (Priority: P2)\naccept text\n")
        with open(os.path.join(self.run_dir, "architecture.md"), "w") as f:
            f.write("# Arch\n\n## Invite service\nservice text\n")

    def tasks_md(self, text):
        with open(self.tasks, "w") as f:
            f.write(text)

    def brief(self, sid):
        path = os.path.join(self.run_dir, "podium", "stories", "M1", f"{sid}.md")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return f.read()

    def test_turns_each_user_story_into_a_story_with_its_brief(self):
        self.data["epics"][0]["milestones"][0]["quality"]["contract"] = [{"cmd": "./gates.sh ."}]
        self.write()
        out = self.podium("breakdown", self.tasks, "--milestone", "M1")
        self.assertEqual(out.splitlines(), [
            "STORY S1 core deps=- files=3 missing=-",
            "STORY S2 core deps=S1 files=2 missing=-",
            "MISSING S2 dep S9",
            "MISSING S2 ref architecture.md#Accept flow",
            "STORY S3 core deps=- files=2 missing=story,critical,context",
            "MISSING S3 story",
            "MISSING S3 critical",
            "MISSING S3 context",
            "OVERLAP S2 S3 src/invites/store.py",
            "WAVES S1 | S2 | S3"])
        stories = {s["id"]: s for s in self.milestone()["stories"]}
        self.assertEqual(list(stories), ["S1", "S2", "S3"])
        self.assertEqual({k: stories["S1"][k] for k in ("title", "summary", "files", "deps", "overlapAfter", "critical", "model", "status", "attempts", "brief")},
                         {"title": "Send an invite", "summary": "An owner sends an invite by email.",
                          "files": ["tests/test_invite.py", "src/invites/service.py", "src/invites/model.py"], "deps": [], "overlapAfter": [],
                          "critical": True, "model": "opus", "status": "todo", "attempts": 0, "brief": "podium/stories/M1/S1.md"})
        self.assertNotIn("repos", stories["S1"])
        self.assertEqual((stories["S2"]["deps"], stories["S2"]["model"]), (["S1"], "opus"))
        self.assertEqual((stories["S3"]["overlapAfter"], stories["S3"]["model"], stories["S3"]["summary"]), (["S2"], "sonnet", "List invites"))
        self.assertEqual(self.events()[-1]["type"], "status")
        brief = self.podium("brief", "S1")
        for want in ("# S1 · Send an invite", "## Goal\nAn owner sends an invite by email. Nothing reads it yet.",
                     "- [ ] T010 Write the failing invite test in tests/test_invite.py",
                     "- [ ] T011 Implement the invite service in `src/invites/service.py`, reusing src/invites/model.py",
                     "## Files in scope\n- tests/test_invite.py\n- src/invites/service.py\n- src/invites/model.py",
                     "- `specs/001-invites/tasks.md#Phase 3: User Story 1 - Send an invite (Priority: P1) 🎯 MVP`",
                     "## Contract\n- `./gates.sh .`", "trailer `Story: S1`", "=== architecture.md § Invite service",
                     "=== specs/001-invites/spec.md § User Story 1 - Send an invite (Priority: P1)",
                     "=== specs/001-invites/tasks.md § Phase 3: User Story 1"):
            self.assertIn(want, brief)
        self.assertNotIn("MISSING", brief)

    def test_a_dry_run_prints_the_same_and_writes_nothing(self):
        before = self.state()
        out = self.podium("breakdown", self.tasks, "--milestone", "M1", "--dry-run")
        self.assertIn("OVERLAP S2 S3 src/invites/store.py\nWAVES S1 | S2 | S3", out)
        self.assertEqual((self.state(), self.events(), self.brief("S1")), (before, [], None))

    def test_a_rerun_updates_each_story_in_place(self):
        self.podium("breakdown", self.tasks, "--milestone", "M1")
        first = self.milestone()["stories"]
        self.tasks_md(TASKS.replace("User Story 2 - Accept an invite", "User Story 2 - Accept or decline"))
        self.podium("breakdown", self.tasks, "--milestone", "M1")
        again = self.milestone()["stories"]
        self.assertEqual([s["id"] for s in again], ["S1", "S2", "S3"])
        self.assertEqual(again[1]["title"], "Accept or decline")
        self.assertEqual([again[0], again[2]], [first[0], first[2]])
        self.assertIn("# S2 · Accept or decline", self.brief("S2"))

    def test_leaves_a_story_already_started_as_it_is(self):
        self.data["epics"][0]["milestones"][0]["stories"] = [
            {"id": "S1", "title": "Old", "status": "working", "deps": [], "attempts": 1}]
        self.write()
        out = self.podium("breakdown", self.tasks, "--milestone", "M1")
        self.assertIn("KEPT S1 started", out.splitlines())
        stories = self.milestone()["stories"]
        self.assertEqual(([s["id"] for s in stories], stories[0]["title"], self.brief("S1")), (["S1", "S2", "S3"], "Old", None))

    def test_a_dependency_cycle_is_reported_and_nothing_written(self):
        self.tasks_md(TASKS.replace("Can start after Foundational (Phase 2) - No dependencies on other stories", "needs US2"))
        before = self.state()
        out = self.podium("breakdown", self.tasks, "--milestone", "M1", code=1)
        self.assertEqual(out.splitlines()[-3:], ["WAVES -", "CYCLE S1 S2", "breakdown: the dependencies loop, nothing written"])
        self.assertEqual((self.state(), self.brief("S3")), (before, None))

    def test_a_story_sharing_a_file_waits_for_the_later_story_it_depends_on(self):
        self.tasks_md(TASKS.replace("Can start after Foundational (Phase 2) - No dependencies on other stories", "needs US3")
                      .replace("Depends on US1 and US9 (needs its service)", "independent")
                      .replace("Show the list in src/web/invites.tsx", "Show the list from src/invites/service.py"))
        out = self.podium("breakdown", self.tasks, "--dry-run")
        self.assertEqual([line for line in out.splitlines() if line.startswith(("OVERLAP", "WAVES"))],
                         ["OVERLAP S2 S3 src/invites/service.py", "OVERLAP S2 S3 src/invites/store.py", "WAVES S2 | S3 | S1"])

    def test_a_prefix_names_the_stories_beside_another_milestone(self):
        out = self.podium("breakdown", self.tasks, "--prefix", "W", "--dry-run")
        for want in ("STORY W1 core deps=-", "STORY W2 core deps=W1", "MISSING W2 dep W9", "OVERLAP W2 W3", "WAVES W1 | W2 | W3"):
            self.assertIn(want, out)
        self.assertIn("breakdown <tasks.md>", self.podium("breakdown", self.tasks, "--prefix", "W2", code=1))

    def test_without_a_dependencies_section_every_story_misses_its_deps(self):
        self.tasks_md(TASKS[:TASKS.index("## Dependencies")])
        out = self.podium("breakdown", self.tasks, "--dry-run")
        self.assertEqual([line for line in out.splitlines() if line.endswith(" deps")], ["MISSING S1 deps", "MISSING S2 deps", "MISSING S3 deps"])

    def test_refuses_a_file_without_user_stories_or_an_unknown_milestone(self):
        before = self.state()
        self.assertIn("no milestone 'M9'", self.podium("breakdown", self.tasks, "--milestone", "M9", code=1))
        self.tasks_md("# Tasks\n\n## Phase 1: Setup\n- [ ] T001 Scaffold in src/app.py\n")
        self.assertIn("User Story", self.podium("breakdown", self.tasks, code=1))
        self.assertEqual(self.state(), before)


class Handoff(Run):
    def handoff(self, kind, mid="M1"):
        out = self.podium("handoff", mid, kind)
        path = os.path.join(self.run_dir, "podium", "handoffs", f"{mid}-{kind}.md")
        self.assertEqual(out, f"PROMPT {path} model=opus\n")
        with open(path) as f:
            return f.read()

    def test_plan_resumes_deep_plan_from_the_ledger_in_the_worktree_of_its_branch(self):
        os.makedirs(os.path.join(self.feature, ".deep-plan"))
        with open(os.path.join(self.feature, ".deep-plan", "state.md"), "w") as f:
            f.write("# ledger\n")
        text = self.handoff("plan")
        self.assertTrue(text.startswith(f"Resume `/deep-plan` for milestone M1 (Feat) of epic e from its ledger, "
                                        f"{os.path.join(self.feature, '.deep-plan', 'state.md')}"), text)
        self.assertIn(f"`podium --dir {self.run_dir}`", text)
        self.assertIn("Return at the Phase 2 checkpoint", text)

    def test_ahead_plans_documents_only_on_a_planning_branch_with_placeholders(self):
        self.data["epics"][0]["milestones"].append({"id": "M2", "title": "Later work", "status": "todo", "stories": []})
        self.write()
        text = self.handoff("ahead", "M2")
        for want in ("through its Phase 2 checkpoint, documents only",
                     f"worktree add {os.path.join(self.tmp, 'core-plan-M2')} -b plan/M2-later-work master`",
                     f"`Reservations` in the main ledger, {os.path.join(self.run_dir, 'state.md')}", "`«<kind>:M2:<n>»`",
                     f"Write nothing under {self.run_dir}", "its branch, every placeholder"):
            self.assertIn(want, text)

    def test_gate_runs_deep_plan_from_its_quality_gate_on_the_milestones_branch(self):
        text = self.handoff("gate")
        for want in ('section "Quality gate"', "Phases 4, 5 and 6", f"Branch: feat on master, worktree {self.feature}",
                     "once landed"):
            self.assertIn(want, text)

    def test_refuses_an_unknown_milestone_or_kind(self):
        self.assertIn("no milestone 'M9'", self.podium("handoff", "M9", "plan", code=1))
        self.assertIn("handoff <milestone> plan|ahead|gate|retro", self.podium("handoff", "M1", "review", code=1))
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "podium", "handoffs")))

    def log(self, *events):
        with open(os.path.join(self.run_dir, "podium", "events.jsonl"), "a") as f:
            f.writelines(json.dumps(e) + "\n" for e in events)

    def test_retro_skips_a_milestone_that_built_without_friction(self):
        self.log({"at": ago(90), "type": "planned", "milestone": "M1"},
                 {"at": ago(80), "type": "dispatched", "milestone": "M1", "story": "S1"},
                 {"at": ago(70), "type": "merged", "milestone": "M1", "story": "S1"},
                 {"at": ago(60), "type": "gate", "milestone": "M1", "verdict": "pass"},
                 {"at": ago(50), "type": "retry", "milestone": "M2", "story": "S1"},
                 {"at": ago(40), "type": "failed", "story": "S1"},
                 {"at": ago(30), "type": "landed", "milestone": "M1", "sha": "abc1234"})
        with open(os.path.join(self.run_dir, "podium", "events.jsonl"), "a") as f:
            f.write("not json\n")
        self.assertEqual(self.podium("handoff", "M1", "retro"), "SKIP no friction\n")
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "podium", "handoffs")))

    def test_retro_prompts_on_each_kind_of_friction(self):
        snags = [{"type": "retry", "story": "S1", "attempt": 2, "reason": "RED contract"},
                 {"type": "failed", "story": "S1", "reason": "stopped without committing"},
                 {"type": "conflict", "story": "S2"},
                 {"type": "gate", "verdict": "fixable", "findings": 3},
                 {"type": "approval", "story": "S2", "tool": "Bash"},
                 {"type": "denied", "story": "S2", "tool": "Bash"}]
        for snag in snags:
            with self.subTest(snag["type"]):
                open(os.path.join(self.run_dir, "podium", "events.jsonl"), "w").close()
                event = {"at": ago(50), "milestone": "M1", **snag}
                self.log({"at": ago(90), "type": "planned", "milestone": "M1"}, event)
                self.assertIn(f"- {json.dumps(event)}", self.handoff("retro"))

    def test_retro_prompt_names_its_reading_its_rules_and_how_to_record(self):
        start = ago(90)
        self.log({"at": start, "type": "planned", "milestone": "M1"}, {"at": ago(50), "type": "conflict", "milestone": "M1", "story": "S1"})
        text = self.handoff("retro")
        cli = f"podium --dir {self.run_dir}"
        events = os.path.join(self.run_dir, "podium", "events.jsonl")
        trees = " ".join(f"--cwd {os.path.join(self.tmp, t)}" for t in ("core", "feat", "core-S1", "core-S2"))
        for want in (f"the lines of {events} whose milestone is M1", f"its ledger, {os.path.join(self.feature, '.deep-plan', 'state.md')}",
                     os.path.join(self.run_dir, "podium", "stories", "M1", "*.progress"),
                     f"`{cli} tokens --since {start} {trees}`",
                     f"First run `{cli} findings --all`", "cites a specific moment", "→ fix `check`", "`standard`",
                     "`pointer` or `access`", "(`delete`)", "No findings is a valid answer",
                     f"{cli} finding add --key <kebab-slug> --kind retro|tokens --target", "--title", "--moment",
                     "--fix check|pointer|standard|delete|access|script|flag|brief|model|tool --severity high|normal",
                     "[--saving <tokens/week, tokens kind only>] --milestone M1", "Reply with the FINDING lines it printed only"):
            self.assertIn(want, text)


class Recur(Run):
    """turn, in process, with a stub `podium` whose `findings --recur` prints `findings`."""

    def turn(self, findings, code=0):
        stub = os.path.join(self.tmp, "podium-stub.py")
        with open(stub, "w") as f:
            f.write("import os, sys\nif sys.argv[1] == 'self-update':\n    print('OK podium abc1234')\n    sys.exit(0)\n"
                    f"open({os.path.join(self.tmp, 'recur-cwd')!r}, 'w').write(os.getcwd())\n"
                    f"sys.stdout.write({''.join(l + chr(10) for l in findings)!r})\n"
                    f"print('podium: findings failed hard', file=sys.stderr)\nsys.exit({code})\n")
        ext, out = self.ext(), io.StringIO()
        with unittest.mock.patch.object(ext, "PODIUM", [sys.executable, stub]), contextlib.redirect_stdout(out):
            ext.cmd_turn(Podium(self.run_dir), [])
        return out.getvalue().splitlines()

    def test_runs_in_the_run_dir_so_podium_finds_the_run_wherever_the_turn_started(self):
        self.turn([])
        with open(os.path.join(self.tmp, "recur-cwd")) as f:
            self.assertEqual(os.path.realpath(f.read()), self.run_dir)

    def test_recurring_findings_follow_the_self_update_lines(self):
        recur = ["RECUR merge-red-on-lint \u00d73 \u2014 the contract's lint runs only at merge"]
        out = self.turn(recur)
        self.assertEqual(out[:2], ["OK podium abc1234", *recur])

    def test_no_recurring_finding_prints_nothing(self):
        self.assertFalse([l for l in self.turn([]) if "findings" in l or l.startswith("RECUR")])

    def test_an_older_podium_without_findings_is_skipped_silently(self):
        out = self.turn(["podium: unknown command 'findings'"], code=2)
        self.assertFalse([l for l in out if "findings" in l or l.startswith("RECUR")], out)

    def test_a_failing_findings_warns_and_the_turn_goes_on(self):
        out = self.turn([], code=1)
        self.assertEqual(out[1], "WARN findings podium: findings failed hard")
        self.assertTrue(any(l.startswith("SYNC") or l.startswith("FF") for l in out), out)


class Bases(Run):
    def advance_origin(self):
        other = self.other_clone()
        return commit(other, "b.txt", "upstream"), git(other, "push", "-q", "origin", "master")

    def test_fast_forwards_a_clean_checkout_on_its_base(self):
        new, _ = self.advance_origin()
        out = self.podium("turn")
        self.assertIn("FF core master", out)
        self.assertEqual(git(self.main, "rev-parse", "master"), new)
        self.assertTrue(os.path.exists(os.path.join(self.main, "b.txt")))

    def test_leaves_a_dirty_checkout_alone(self):
        before = git(self.main, "rev-parse", "master")
        self.advance_origin()
        with open(os.path.join(self.main, "a.txt"), "w") as f:
            f.write("edited")
        out = self.podium("turn")
        self.assertIn(f"BEHIND core master 1: {self.main} has changes", out)
        self.assertEqual(git(self.main, "rev-parse", "master"), before)

    def test_moves_a_base_no_worktree_has_checked_out_as_a_bare_ref(self):
        git(self.main, "switch", "-q", "-c", "elsewhere")
        new, _ = self.advance_origin()
        self.assertIn("FF core master", self.podium("turn"))
        self.assertEqual(git(self.main, "rev-parse", "master"), new)
        self.assertEqual(git(self.main, "rev-parse", "--abbrev-ref", "HEAD"), "elsewhere")

    def test_never_moves_a_diverged_base(self):
        mine = commit(self.main, "c.txt", "local only")
        self.advance_origin()
        self.assertIn("BEHIND core master 1: diverged, 1 local commits", self.podium("turn"))
        self.assertEqual(git(self.main, "rev-parse", "master"), mine)

    def test_a_moved_milestones_missing_checkout_is_not_reported(self):
        self.data["epics"][0]["milestones"].append({"id": "M2", "status": "moved", "movedTo": "M1", "repos": {
            "x": {"path": os.path.join(self.tmp, "gone"), "base": "master"}}})
        self.write()
        self.assertNotIn("MISSING", self.podium("turn"))

    def test_says_every_repo_is_up_to_date_when_nothing_moved(self):
        self.assertIn("SYNC 1 repos up to date", self.podium("turn").splitlines())

    def test_refuses_a_checkout_a_pull_may_have_written(self):
        planted, marker = os.path.join(self.run_dir, "podium", "stories", "x"), os.path.join(self.tmp, "marker")
        git(self.tmp, "init", "-q", "--bare", planted)
        git(planted, "config", "remote.origin.url", "ssh://example.invalid/x")
        git(planted, "config", "core.sshCommand", f"touch {marker}; false")
        self.data["epics"][0]["milestones"][0]["repos"] = {"x": {"path": "podium/stories/x", "base": "master"}}
        self.write()
        self.assertEqual(self.podium("turn", code=1).splitlines()[-1], "refused checkout podium/stories/x: in the run dir outside repos/ and worktrees/")
        self.assertFalse(os.path.exists(marker))


class Pull(Run):
    def test_turn_starts_with_syncs_pull_line_and_reads_what_it_pulled(self):
        def pull(p):
            self.data["project"]["title"] = "Pulled"
            self.write()
            return "PULLED abc1234"

        ext = self.ext()
        with unittest.mock.patch.object(ext.sync, "pull", pull), unittest.mock.patch.object(ext, "PODIUM", [sys.executable, "-c", ""]):
            out = self.podium("turn").splitlines()
        self.assertEqual(out[0], "PULLED abc1234")
        self.assertIn("Pulled · active e/M1", out)
        self.assertEqual(self.state()["project"]["title"], "Pulled")


class Landing(Run):
    def story_commit(self):
        sha = commit(self.feature, "f.txt", "feat: one\n\nStory: S1")
        git(self.feature, "push", "-q", "origin", "feat")
        m = self.data["epics"][0]["milestones"][0]
        m["stories"][0]["status"] = "done"  # its commits come only from the trailer
        m["pr"] = {"number": 7, "url": "https://github.com/o/core/pull/7", "state": "merged"}
        m["asana"] = {"gid": "42"}
        self.write()
        return sha

    def landed_turn(self):
        """`turn`'s lines and the merge commit once M1 landed on origin, with no plugins in the podium."""
        other = self.other_clone()
        git(other, "merge", "-q", "--no-ff", "-m", "Merge feat", "origin/feat")
        git(other, "push", "-q", "origin", "master")
        with unittest.mock.patch.dict(sys.modules, {"podium_dashboard.plugins": None}):
            return self.podium("turn").splitlines(), git(other, "rev-parse", "HEAD")

    def test_records_a_milestone_merged_on_origin_as_done(self):
        sha = self.story_commit()
        out, merge = self.landed_turn()
        self.assertIn(f"LANDED M1 {merge[:7]}", "\n".join(out))
        self.assertIn("ACT asana-complete M1 42", out)
        self.assertEqual(len([l for l in out if l.startswith("ASANA-UNAVAILABLE")]), 1)
        m = self.milestone()
        self.assertEqual((m["status"], m["landedSha"]), ("done", merge[:10]))
        self.assertEqual(m["stories"][0]["commits"][0]["sha"], sha[:10])
        self.assertIsNone(self.state()["active"])
        self.assertEqual([(e["type"], e["sha"]) for e in self.events() if e["type"] == "landed"], [("landed", merge[:10])])

    def test_a_branch_without_work_has_not_landed(self):
        self.assertNotIn("LANDED", self.podium("turn"))
        self.assertEqual(self.milestone()["status"], "working")

    def test_a_moved_milestone_is_never_recorded_as_landed(self):
        self.story_commit()
        self.data["epics"][0]["milestones"][0].update(status="moved", movedTo="M2")
        self.write()
        out, _ = self.landed_turn()
        self.assertEqual([l for l in out if l.startswith(("LANDED", "PR M1"))], [])
        self.assertEqual(self.milestone()["status"], "moved")
        self.assertNotIn("landed", [e["type"] for e in self.events()])

    def test_a_squash_merged_pr_lands_through_gh(self):
        sha = self.story_commit()
        del self.data["epics"][0]["milestones"][0]["asana"]
        self.data["epics"][0]["milestones"][0]["pr"]["state"] = "open"
        self.write()
        self.fake("gh", """echo '{"state": "MERGED", "isDraft": false, "url": "https://github.com/o/core/pull/7",
              "mergeCommit": {"oid": "abcdef1234567890"}, "mergedAt": "2026-10-12T10:00:00Z"}'""")
        out = self.podium("turn")
        self.assertIn("PR M1 #7 merged (was open)", out)
        self.assertIn("LANDED M1 abcdef1 2026-10-12", out)
        self.assertEqual(self.milestone()["stories"][0]["commits"][0]["sha"], sha[:10])


    def test_asks_to_complete_no_asana_gid_that_is_not_all_digits(self):
        self.story_commit()
        self.data["epics"][0]["milestones"][0]["asana"] = {"gid": "42\x1b[2J"}
        self.write()
        out, _ = self.landed_turn()
        self.assertIn("refused asana gid '42\\x1b[2J': not all digits", out)
        self.assertEqual([l for l in out if "asana-complete" in l or "\x1b" in l], [])


class Ownership(Run):
    """M1 owned by bob; this person is alice."""

    def setUp(self):
        super().setUp()
        os.environ["PODIUM_ME"] = "alice"
        self.data["epics"][0]["milestones"][0]["owner"] = "bob"
        self.write()

    def test_verbs_that_change_a_milestone_refuse_one_another_person_owns(self):
        for verb in ("launch", "merge", "land"):
            self.assertIn("milestone M1 is owned by bob", self.podium(verb, "S1", code=1))
        self.assertFalse(os.path.exists(f"{self.main}-S1"))
        self.assertEqual(self.milestone()["stories"][0]["status"], "todo")
        self.assertEqual(self.events(), [])

    def test_force_launches_a_story_of_another_persons_milestone(self):
        self.assertTrue(self.podium("launch", "S1", "--force").startswith("PROMPT "))
        self.assertEqual(self.milestone()["stories"][0]["status"], "working")

    def test_a_milestone_of_ones_own_launches(self):
        self.data["epics"][0]["milestones"][0]["owner"] = "alice"
        self.write()
        self.assertTrue(self.podium("launch", "S1").startswith("PROMPT "))

    def land_on_origin(self):
        commit(self.feature, "f.txt", "feat: one\n\nStory: S1")
        git(self.feature, "push", "-q", "origin", "feat")
        self.data["epics"][0]["milestones"][0]["pr"] = {"number": 7, "state": "merged"}
        self.write()
        other = self.other_clone()
        git(other, "merge", "-q", "--no-ff", "-m", "Merge feat", "origin/feat")
        git(other, "push", "-q", "origin", "master")

    def test_turn_leaves_another_persons_landing_to_them(self):
        self.land_on_origin()
        self.assertIn("SKIP-LANDED M1: milestone M1 is owned by bob", self.podium("turn").splitlines())
        self.assertEqual(self.milestone()["status"], "working")
        self.assertIn("LANDED M1", self.podium("turn", "--force"))
        self.assertEqual(self.milestone()["status"], "done")

    def test_a_landing_clears_only_this_persons_active_milestone(self):
        self.land_on_origin()
        self.data["epics"][0]["milestones"][0]["owner"] = "alice"
        self.data["people"] = {"alice": {"active": {"epic": "e", "milestone": "M1"}}, "bob": {"active": {"milestone": "M1"}}}
        del self.data["active"]
        self.write()
        self.assertIn("LANDED M1", self.podium("turn"))
        people = self.state()["people"]
        self.assertEqual((people["alice"]["active"], people["bob"]["active"]), (None, {"milestone": "M1"}))
        self.assertNotIn("active", self.state())

    def test_a_bare_story_id_resolves_in_this_persons_active_milestone(self):
        self.data["people"] = {"alice": {"active": {"epic": "e", "milestone": "M1"}}}
        del self.data["active"]
        self.write()
        self.assertTrue(self.ext().prompt(Podium(self.run_dir), "assign", "S1").startswith("You build one story"))


class AutoClaim(Run):
    """A run that syncs to origin, its milestone M1 owned by nobody; this person is alice."""

    def setUp(self):
        super().setUp()
        os.environ["PODIUM_ME"] = "alice"
        self.data["sync"] = {"enabled": True, "remote": "origin", "ref": "refs/heads/podium-run/core"}
        self.write()

    def synced_owner(self):
        shown = git(self.tmp, "--git-dir", self.origin, "show", "refs/heads/podium-run/core:podium/podium.json")
        return json.loads(shown)["epics"][0]["milestones"][0].get("owner")

    def saved_elsewhere(self):
        """This run saved, then another machine joined it and saved a note on M1, so a claim here pulls it in."""
        self.podium("sync", "save", "start")
        there = os.path.join(self.other_clone(), ".deep-plan")
        os.makedirs(there)
        for args in (("sync", "on", "--ref", "refs/heads/podium-run/core"), ("sync", "pull"),
                     ("set", "milestone:M1", "note=from elsewhere"), ("sync", "save", "note")):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.main(["--dir", there, *args])

    def test_merge_claims_an_unowned_milestone_and_keeps_what_it_recorded(self):
        sha = commit(self.story_branch("S1"), "s.txt", "feat: one\n\nStory: S1")
        self.saved_elsewhere()
        out = self.podium("merge", "S1").splitlines()
        self.assertEqual(out[0], "claimed M1")
        self.assertTrue(out[1].startswith("MERGED S1 1 commits"), out)
        m = self.milestone()
        s = m["stories"][0]
        self.assertEqual((m["owner"], m["note"], s["status"], s["commits"][0]["sha"]), ("alice", "from elsewhere", "done", sha[:10]))
        self.assertEqual(self.synced_owner(), "alice")

    def test_land_claims_an_unowned_milestone_and_keeps_the_wave_it_launched(self):
        self.podium("set", "S1", "status=done")
        self.podium("set", "milestone:M1", "buildAll=true")
        self.podium("dispatcher", "agent")
        self.saved_elsewhere()
        out = self.podium("land", "S1", "--next").splitlines()
        self.assertEqual(out[:2], ["claimed M1", "LANDED S1; launched S2"])
        m = self.milestone()
        self.assertEqual((m["owner"], m["stories"][1]["status"]), ("alice", "working"))

    def test_turn_records_a_landing_without_claiming(self):
        commit(self.feature, "f.txt", "feat: one\n\nStory: S1")
        git(self.feature, "push", "-q", "origin", "feat")
        self.data["epics"][0]["milestones"][0]["pr"] = {"number": 7, "state": "merged"}
        self.write()
        other = self.other_clone()
        git(other, "merge", "-q", "--no-ff", "-m", "Merge feat", "origin/feat")
        git(other, "push", "-q", "origin", "master")
        out = self.podium("turn")
        self.assertIn("LANDED M1", out)
        self.assertNotIn("claimed", out)
        self.assertEqual((self.milestone()["status"], self.milestone().get("owner")), ("done", None))


class Requests(Run):
    def queue(self, *lines):
        with open(os.path.join(self.run_dir, "podium", "requests.jsonl"), "a") as f:
            f.writelines(json.dumps(l) + "\n" for l in lines)

    def requests(self):
        return [l for l in self.podium("turn").splitlines() if l.startswith(("ACT", "LIST"))]

    def test_splits_the_users_answers_from_the_rest_and_passes_each_on_once(self):
        self.queue({"action": "confirm", "story": "0,1"}, {"action": "assign", "story": "S1"},
                   {"action": "reverse", "story": "1", "note": "no"}, {"action": "asana-done", "story": "M1", "note": "keep"})
        self.assertEqual(self.requests(), ["ACT confirm 0", "LIST assign S1", "ACT asana-done M1 note=keep"])
        self.assertEqual(self.requests(), [])

    def test_skips_what_the_watcher_already_printed(self):
        self.queue({"action": "assign", "story": "S1"})
        size = os.path.getsize(os.path.join(self.run_dir, "podium", "requests.jsonl"))
        self.podium("turn")
        self.queue({"action": "assign", "story": "S2"})
        path = os.path.join(self.run_dir, "podium", "requests.jsonl")
        with open(os.path.join(self.run_dir, "podium", "watcher.json"), "w") as f:
            json.dump({"at": 0, "offsets": {path: os.path.getsize(path)}, "since": {path: size}}, f)
        self.queue({"action": "plan", "story": "M1"})
        self.assertEqual([l for l in self.requests() if l.startswith("LIST")], ["LIST plan M1"])

    def test_lists_the_podiums_share_request_and_gives_it_the_join_steps(self):
        self.queue({"action": "share", "story": None})
        self.assertEqual(self.requests(), ["LIST share"])
        steps = [s.format(ref="refs/heads/podium-run/app")
                 for s in extension.share_steps(extension.load(Podium(self.run_dir))[0])]
        self.assertEqual(steps, [
            "Clone this run's repo if you haven't: git clone <url>",
            "Install the podium tool (pip3 install --user git+https://github.com/warriv93/podium-dashboard) and the "
            "orchestrate-deep-plans skill (clone https://github.com/warriv93/deep-skills and run its ./install.sh; "
            "see its README)",
            "In your clone, start claude and run /orchestrate-deep-plans join refs/heads/podium-run/app",
            "Claim a milestone: podium claim <id>"])

    def test_drops_asana_done_for_a_milestone_dropped_moved_or_kept_open_meanwhile(self):
        self.data["epics"][0]["milestones"] += [{"id": "M2", "status": "dropped"}, {"id": "M3", "status": "todo", "asana": {"keep": True}},
                                                {"id": "M4", "status": "moved", "movedTo": "M1"}]
        self.write()
        self.queue(*({"action": "asana-done", "story": mid} for mid in ("M1", "M2", "M3", "M4")))
        with unittest.mock.patch.dict(sys.modules, {"podium_dashboard.plugins": None}):
            self.assertEqual(self.requests(), ["ACT asana-done M1"])


class Launch(Run):
    def test_dispatches_a_ready_story_as_a_prompt_for_the_agent_tool(self):
        out = self.podium("launch", "S1", "S2")
        prompt = os.path.join(self.run_dir, "podium", "stories", "M1", "S1.prompt")
        self.assertEqual(out.splitlines(), [f"PROMPT {prompt} model=opus", "SKIP S2 waits on S1"])
        tree = f"{self.main}-S1"
        self.assertEqual(git(tree, "rev-parse", "--abbrev-ref", "HEAD"), "story/S1")
        s = self.milestone()["stories"][0]
        self.assertEqual((s["status"], s["attempts"], s["worktrees"]), ("working", 1, {"core": tree}))
        with open(prompt) as f:
            text = f.read()
        self.assertIn(f"podium --dir {self.run_dir} brief M1/S1", text)
        self.assertIn(f"core: {tree}", text)
        self.assertIn(f"{self.run_dir}/podium/stories/M1/S1.progress", text)
        self.assertEqual([e["type"] for e in self.events()], ["dispatched"])

    def paseo(self):
        log = os.path.join(self.tmp, "paseo.log")
        os.environ["PODIUM_PASEO"] = self.fake("paseo", f"""echo "$@" >> {log}
            case "$1 $2" in
              "provider models") echo '[{{"id": "claude-opus-5-5"}}, {{"id": "claude-sonnet-5-5[1m]"}}, {{"id": "claude-sonnet-5-5"}}]';;
              "workspace create") echo '{{"workspaceId": "wks_1"}}';;
              "workspace archive") echo '{{"status": "archived"}}';;
              run*) echo '{{"agentId": "agent-1234567890"}}';;
            esac""")
        self.data["dispatcher"] = "paseo"
        self.write()
        return log

    def test_runs_a_paseo_agent_with_the_story_in_its_environment(self):
        log = self.paseo()
        self.assertEqual(self.podium("launch", "S1").strip(), "LAUNCHED S1 paseo agent=agent-12 model=claude/claude-opus-5-5")
        with open(log) as f:
            run = next(l for l in f if l.startswith("run"))
        for want in ("--mode auto", "--provider claude/claude-opus-5-5", "PODIUM_STORY=S1", "PODIUM_MILESTONE=M1", "--workspace wks_1"):
            self.assertIn(want, run)
        self.assertEqual(self.milestone()["stories"][0]["agent"], {"backend": "paseo", "id": "agent-1234567890", "workspace": "wks_1"})

    def test_a_paseo_failure_undoes_the_worktree_and_records_nothing(self):
        self.data["dispatcher"] = "paseo"
        self.data["epics"][0]["milestones"][0]["stories"][0]["model"] = "claude-opus-5-5"  # no lookup: the module keeps Paseo's model list
        self.write()
        out = self.podium("launch", "S1")
        self.assertEqual(out.strip(), "FAILED S1 paseo: no paseo here")
        self.assertFalse(os.path.exists(f"{self.main}-S1"))
        self.assertEqual(self.milestone()["stories"][0]["status"], "todo")
        self.assertEqual(self.events(), [])

    def test_land_retires_the_story_and_launches_the_next_wave(self):
        log = self.paseo()
        self.podium("launch", "S1")
        self.podium("set", "S1", "status=done")
        self.podium("set", ".", "buildAll=true")
        out = self.podium("land", "S1", "--next")
        self.assertEqual(out.splitlines()[0], "LANDED S1; launched S2")
        self.assertFalse(os.path.exists(f"{self.main}-S1"))
        with open(log) as f:
            self.assertIn("workspace archive wks_1 --json\n", f.readlines())
        self.assertEqual(self.milestone()["stories"][1]["status"], "working")

    def dispatchers(self):
        with open(os.path.join(self.tmp, "dispatcher.json")) as f:
            return json.load(f)

    def test_this_machines_dispatcher_runs_the_story_on_paseo(self):
        self.paseo()
        self.data["dispatcher"] = "agent"
        self.write()
        self.assertEqual(self.podium("dispatcher", "paseo"), "DISPATCHER paseo\n")
        self.assertEqual(self.podium("launch", "S1").strip(), "LAUNCHED S1 paseo agent=agent-12 model=claude/claude-opus-5-5")
        self.assertEqual(self.dispatchers(), {self.run_dir: "paseo"})

    def test_an_unsynced_runs_dispatcher_moves_to_this_machine_once(self):
        self.paseo()
        self.assertTrue(self.podium("launch", "S1").startswith("LAUNCHED S1 paseo"))
        self.data = self.state()
        self.data["dispatcher"] = "agent"
        self.data["epics"][0]["milestones"][0]["stories"][0]["status"] = "done"
        self.write()
        self.assertTrue(self.podium("launch", "S2").startswith("LAUNCHED S2 paseo"))
        self.assertEqual(self.dispatchers(), {self.run_dir: "paseo"})

    def test_a_pulled_dispatcher_leaves_launch_on_the_agent_tool(self):
        log = self.paseo()
        os.environ["PODIUM_ME"] = "alice"
        m = self.data["epics"][0]["milestones"][0]
        self.data["dispatcher"], m["owner"] = "agent", "alice"
        self.data["sync"] = {"enabled": True, "remote": "origin", "ref": "refs/heads/podium-run/core"}
        self.write()
        self.podium("sync", "save", "start")
        there = os.path.join(self.other_clone(), ".deep-plan")
        os.makedirs(there)
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(["--dir", there, "sync", "on", "--ref", "refs/heads/podium-run/core"])
            cli.main(["--dir", there, "sync", "pull"])
            with open(os.path.join(there, "podium", "podium.json")) as f:
                theirs = json.load(f)
            with open(os.path.join(there, "podium", "podium.json"), "w") as f:
                json.dump({**theirs, "dispatcher": "paseo"}, f)
            cli.main(["--dir", there, "sync", "save", "paseo"])
        self.assertTrue(self.podium("sync", "pull").startswith("PULLED"))
        self.assertEqual(self.state()["dispatcher"], "paseo")
        prompt = os.path.join(self.run_dir, "podium", "stories", "M1", "S1.prompt")
        self.assertEqual(self.podium("launch", "S1").splitlines(),
                         ["DISPATCHER agent (podium dispatcher paseo to use Paseo)", f"PROMPT {prompt} model=opus"])
        self.assertFalse(os.path.exists(log))
        self.assertEqual(self.dispatchers(), {self.run_dir: "agent"})

    def test_dispatcher_refuses_anything_but_paseo_or_agent(self):
        self.assertEqual(self.podium("dispatcher", "sh", code=1), "dispatcher paseo | agent\n")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "dispatcher.json")))

    def test_a_retry_keeps_a_worktree_with_changes(self):
        self.podium("launch", "S1")
        tree = f"{self.main}-S1"
        with open(os.path.join(tree, "half.txt"), "w") as f:
            f.write("unfinished")
        self.assertTrue(self.podium("launch", "S1", "--retry", "red contract").startswith(f"SKIP S1 KEPT {tree}:"))
        self.assertTrue(os.path.exists(os.path.join(tree, "half.txt")))

    def test_a_retry_starts_the_story_branch_afresh(self):
        self.podium("launch", "S1")
        tree = f"{self.main}-S1"
        commit(tree, "bad.txt", "attempt 1")
        self.podium("launch", "S1", "--retry", "red contract")
        self.assertEqual(git(tree, "rev-parse", "HEAD"), git(self.feature, "rev-parse", "HEAD"))
        s = self.milestone()["stories"][0]
        self.assertEqual(s["attempts"], 2)
        with open(os.path.join(self.run_dir, "podium", "stories", "M1", "S1.prompt")) as f:
            self.assertIn("Previous attempt failed: red contract", f.read())
        self.assertEqual([e["type"] for e in self.events()], ["dispatched", "retry", "dispatched"])

    def test_a_retry_reopens_the_stories_its_failure_blocked(self):
        self.podium("launch", "S1")
        self.podium("set", "S1", "status=failed")
        self.assertEqual(self.milestone()["stories"][1]["status"], "blocked")
        self.podium("launch", "S1", "--retry", "red contract")
        self.assertEqual([s["status"] for s in self.milestone()["stories"]], ["working", "todo"])

    def test_land_refuses_a_story_not_merged(self):
        self.assertEqual(self.podium("land", "S1", code=1).strip(), "NOT-MERGED S1 todo")

    def test_launches_and_lands_a_story_on_a_checkout_relative_to_the_run_dir(self):
        git(self.main, "worktree", "add", "-q", "--detach", os.path.join(self.run_dir, "repos", "core"), "master")
        m = self.data["epics"][0]["milestones"][0]
        m["repos"], m["stories"][0]["repos"] = {"core": {"path": "repos/core", "branch": "feat"}}, ["core"]
        self.write()
        self.assertTrue(self.podium("launch", "S1").startswith("PROMPT "))
        tree = os.path.join(self.run_dir, "worktrees", "S1", "core")
        self.assertEqual(git(tree, "rev-parse", "--abbrev-ref", "HEAD"), "story/S1")
        self.podium("set", "S1", "status=done")
        self.assertEqual(self.podium("land", "S1").splitlines()[0], "LANDED S1")
        self.assertFalse(os.path.exists(tree))


class Peek(Run):
    """S1 working on a Paseo agent with a progress file; S2 merged; times relative to now."""

    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.tmp, "paseo.log")
        self.agents = os.path.join(self.tmp, "agents.json")
        self.agents_are([{"id": "agent-1234567890", "status": "running"}])
        os.environ["PODIUM_PASEO"] = self.fake("paseo", f'echo "$@" >> {self.log}\n[ "$1" = ls ] && cat {self.agents}\n')
        m = self.data["epics"][0]["milestones"][0]
        m["stories"][0].update(status="working", startedAt=ago(14), agent={"backend": "paseo", "id": "agent-1234567890"},
                               worktrees={"core": f"{self.main}-S1"})
        m["stories"][1].update(status="done", startedAt=ago(200), finishedAt=ago(125), commits=[{"sha": "1a2b3c4d5e"}])
        self.write()
        self.progress("STARTED", 30, "", "COMMITTED", 25, "0123456789", "STARTED", 14, "", "RED", 5, "", "GREEN", 3, "")

    def agents_are(self, agents):
        with open(self.agents, "w") as f:
            json.dump(agents, f)

    def progress(self, *rows):
        path = os.path.join(self.run_dir, "podium", "stories", "M1", "S1.progress")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for stage, minutes, note in zip(rows[::3], rows[1::3], rows[2::3]):
                f.write(f"{ago(minutes)} {stage} {note}".rstrip() + "\n")

    def test_a_working_story_shows_its_stage_and_live_agent_and_no_commit_of_an_earlier_attempt(self):
        before = self.state()
        self.assertEqual(self.podium("peek", "S1"),
                         "M1/S1 working 14m · RED→GREEN 3m ago · gates - · agent alive (paseo agent-12) · commit -\n")
        self.assertEqual(self.state(), before)
        self.assertEqual(self.events(), [])

    def test_a_committed_story_shows_its_commit_and_this_attempts_gates(self):
        self.progress("STARTED", 14, "", "CONTRACT", 2, "", "COMMITTED", 1, "abcdef1234")
        self.data["epics"][0]["milestones"][0]["quality"]["contract"] = [
            {"cmd": "a", "ok": False, "at": ago(0), "story": "S1"},
            {"cmd": "b", "ok": True, "at": ago(20), "story": "S1"},
            {"cmd": "c", "ok": True, "at": ago(0), "story": "S2"}]
        self.write()
        out = self.podium("peek", "S1", "M1/S2").splitlines()
        self.assertEqual(out, ["M1/S1 working 14m · CONTRACT→COMMITTED 1m ago · gates contract✗ · agent alive (paseo agent-12)"
                               " · committed abcdef1",
                               "M1/S2 done 2h5m ago · progress - · gates contract✓ · agent - · committed 1a2b3c4"])
        with open(self.log) as f:
            self.assertEqual(f.read(), "ls -g --json\n")

    def test_an_agent_paseo_no_longer_lists_is_dead(self):
        self.agents_are([{"id": "agent-other", "status": "running"}])
        self.assertIn(" · agent dead (paseo agent-12) · ", self.podium("peek", "S1"))
        self.agents_are([{"id": "agent-1234567890", "status": "idle"}])
        self.assertIn(" · agent idle (paseo agent-12) · ", self.podium("peek", "S1"))

    def test_an_agent_tool_story_counts_the_processes_in_its_worktree(self):
        self.podium("set", "S1", "agent.backend=agent")
        self.fake("lsof", f"printf 'p1\\nfcwd\\nn{self.main}-S1/sub\\np2\\nfcwd\\nn{self.main}-S10\\np3\\nfcwd\\nn{self.tmp}\\n'")
        self.assertIn(" · agent local (1 procs in worktree) · ", self.podium("peek", "S1"))

    def test_an_unknown_story_says_so(self):
        self.assertEqual(self.podium("peek", "S9", "M7/S1"), "PEEK S9 unknown\nPEEK M7/S1 unknown\n")


class TwoMilestones(Run):
    """M2 builds beside the active M1 on branch feat2, checked out in its own worktree plan-m2/ as a milestone planned
    ahead keeps it, with stories T1 and T2 (T2 after T1)."""

    def setUp(self):
        super().setUp()
        self.m2_tree = os.path.join(self.tmp, "plan-m2")
        git(self.main, "worktree", "add", "-q", "-b", "feat2", self.m2_tree, "master")
        self.data["epics"][0]["milestones"].append({
            "id": "M2", "title": "Beside", "status": "working", "phase": "build", "branch": "feat2", "pr": None,
            "quality": {"contract": []},
            "stories": [{"id": "T1", "title": "Ten", "status": "todo", "deps": [], "model": "sonnet", "attempts": 0},
                        {"id": "T2", "title": "Eleven", "status": "todo", "deps": ["T1"], "model": "sonnet", "attempts": 0}]})
        self.write()

    def m2(self):
        return self.state()["epics"][0]["milestones"][1]

    def test_land_next_launches_the_next_wave_of_the_storys_own_milestone(self):
        self.podium("set", "milestone:M2", "buildAll=true")
        self.podium("set", "M2/T1", "status=done")
        out = self.podium("land", "M2/T1", "--next")
        self.assertEqual(out.splitlines()[0], "LANDED T1; launched T2")
        self.assertEqual(self.m2()["stories"][1]["status"], "working")
        self.assertEqual(git(f"{self.main}-T2", "rev-parse", "HEAD"), git(self.m2_tree, "rev-parse", "HEAD"))
        self.podium("set", "S1", "status=done")
        self.assertEqual(self.podium("land", "S1", "--next").splitlines()[0], "LANDED S1; buildAll off")

    def wait_for_m1(self):
        self.podium("set", "milestone:M2", "buildAll=true")
        self.podium("set", "milestone:M2", 'waitsFor=[{"milestone":"M1","reason":"needs its schema"}]')
        self.podium("set", "M2/T1", "status=done")

    def test_land_next_holds_the_wave_of_a_milestone_that_waits_for_another(self):
        self.wait_for_m1()
        out = self.podium("land", "M2/T1", "--next").splitlines()
        self.assertEqual(out[0], "LANDED T1; wave held")
        self.assertIn("WAITING M2 for M1", out)
        self.assertEqual(self.m2()["stories"][1]["status"], "todo")

    def test_land_next_launches_the_wave_once_the_user_went_ahead(self):
        self.wait_for_m1()
        self.podium("set", "milestone:M2", "waitsForAck=true")
        out = self.podium("land", "M2/T1", "--next").splitlines()
        self.assertEqual(out[0], "LANDED T1; launched T2")
        self.assertNotIn("WAITING M2 for M1", out)
        self.assertEqual(self.m2()["stories"][1]["status"], "working")

    def test_land_next_launches_when_the_only_awaited_milestone_is_done(self):
        self.wait_for_m1()
        self.podium("set", "milestone:M1", "status=done")
        out = self.podium("land", "M2/T1", "--next").splitlines()
        self.assertEqual(out[0], "LANDED T1; launched T2")
        self.assertNotIn("WAITING M2 for M1", out)

    def test_a_manual_launch_works_and_notes_the_wait(self):
        self.podium("set", "milestone:M2", 'waitsFor=[{"milestone":"M1","reason":"needs its schema"}]')
        out = self.podium("launch", "M2/T1").splitlines()
        self.assertEqual(out[0], "NOTE M2 is waiting for M1; launching anyway")
        self.assertTrue(out[1].startswith(("LAUNCHED T1", "PROMPT ")), out)
        self.assertEqual(self.m2()["stories"][0]["status"], "working")

    def wait_for_moved(self, *moves):
        """M2 waits for M3, and each (id, target) in `moves` is a milestone folded into its target."""
        self.data["epics"][0]["milestones"] += [{"id": mid, "status": "moved", "movedTo": to} for mid, to in moves]
        self.write()
        self.podium("set", "milestone:M2", "buildAll=true")
        self.podium("set", "milestone:M2", 'waitsFor=[{"milestone":"M3","reason":"needs its schema"}]')
        self.podium("set", "M2/T1", "status=done")

    def test_a_wait_on_a_moved_milestone_waits_for_the_milestone_it_moved_to(self):
        self.wait_for_moved(("M3", "M4"), ("M4", "M1"))
        out = self.podium("land", "M2/T1", "--next").splitlines()
        self.assertEqual(out[0], "LANDED T1; wave held")
        self.assertIn("WAITING M2 for M1 (was M3)", out)

    def test_a_wait_on_a_moved_milestone_is_met_once_its_final_target_is_done(self):
        self.wait_for_moved(("M3", "M4"), ("M4", "M1"))
        self.podium("set", "milestone:M1", "status=done")
        self.assertEqual(self.podium("land", "M2/T1", "--next").splitlines()[0], "LANDED T1; launched T2")

    def test_a_cycle_of_moves_ends_and_keeps_the_wait(self):
        self.wait_for_moved(("M3", "M4"), ("M4", "M3"))
        out = self.podium("land", "M2/T1", "--next").splitlines()
        self.assertEqual(out[0], "LANDED T1; wave held")
        self.assertIn("WAITING M2 for M4 (was M3)", out)

    def test_a_wait_on_a_milestone_moved_into_the_waiting_one_is_met(self):
        self.wait_for_moved(("M3", "M2"))
        self.assertEqual(self.podium("land", "M2/T1", "--next").splitlines()[0], "LANDED T1; launched T2")

    def test_a_manual_launch_notes_the_final_target_of_a_moved_wait(self):
        self.wait_for_moved(("M3", "M1"))
        self.podium("set", "M2/T1", "status=todo")
        self.assertEqual(self.podium("launch", "M2/T1").splitlines()[0], "NOTE M2 is waiting for M1 (was M3); launching anyway")

    def test_merges_a_story_of_another_milestone_in_the_worktree_of_its_branch(self):
        sha = commit(self.story_branch("T1", "feat2"), "t.txt", "feat: ten\n\nStory: T1")
        self.assertEqual(self.podium("merge", "M2/T1").splitlines()[0], "MERGED T1 1 commits; ready: T2")
        self.assertEqual(self.m2()["stories"][0]["commits"][0]["sha"], sha[:10])
        self.assertTrue(os.path.exists(os.path.join(self.m2_tree, "t.txt")))
        self.assertEqual(git(self.main, "rev-parse", "--abbrev-ref", "HEAD"), "master")
        self.assertFalse(os.path.exists(os.path.join(self.feature, "t.txt")))

    def test_peek_finds_a_bare_story_of_the_one_milestone_that_has_it(self):
        self.assertEqual(self.podium("peek", "T1"), "M2/T1 todo · progress - · gates - · agent - · commit -\n")

    def serve(self):
        """A Podium on a free port that knows this run and releases hand-offs, its URL in server.log as the
        server writes it."""
        run_dir, handoffs = self.run_dir, os.path.join(self.run_dir, "podium", "handoffs.json")

        class Handler(BaseHTTPRequestHandler):
            def answer(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self.answer({"runDir": run_dir, "watching": True})

            def do_DELETE(self):
                with open(handoffs) as f:
                    taken = json.load(f)
                key = self.path[len("/handoff/"):]
                taken.pop(key, None)
                with open(handoffs, "w") as f:
                    json.dump(taken, f)
                self.answer({"released": key})

            def log_message(self, *_):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        url = f"http://127.0.0.1:{httpd.server_address[1]}/"
        with open(os.path.join(self.run_dir, "podium", "server.log"), "w") as f:
            f.write(f"12:00 serving {url}\n")
        return url

    def handoffs(self):
        with open(os.path.join(self.run_dir, "podium", "handoffs.json")) as f:
            return json.load(f)

    def test_a_handed_off_story_of_another_milestone_gets_its_worktree_step_and_is_released_on_land(self):
        url = self.serve()
        with open(os.path.join(self.run_dir, "podium", "handoffs.json"), "w") as f:
            json.dump({"M2/T1": {"at": "2026-10-20T08:00:00+00:00"}}, f)
        text = self.ext().prompt(Podium(self.run_dir), "handoff", "M2/T1")
        self.assertIn(f"git -C {self.main} worktree add -b story/T1 {self.main}-T1 feat2", text)
        self.assertIn(f"podium --dir {self.run_dir} brief M2/T1", text)
        self.assertEqual(self.podium("ready", "--milestone", "M2").strip(), "")
        self.podium("set", "M2/T1", "status=done")
        self.assertEqual(self.podium("land", "M2/T1").splitlines(), ["LANDED T1", "RELEASED T1"])
        self.assertEqual(self.handoffs(), {})
        self.assertIn(f"PODIUM up {url} watching", self.podium("turn").splitlines())


class Untrusted(Run):
    """Values a pull may have written into podium.json: none becomes a path outside the run's own or a git option."""

    def test_launch_refuses_a_repo_name_that_is_a_path(self):
        escaped = os.path.join(self.tmp, "escaped")
        for name in ("../../../../escaped", escaped):
            with self.subTest(name=name):
                m = self.data["epics"][0]["milestones"][0]
                m["repos"], m["stories"][0]["repos"] = {name: {"path": self.main, "branch": "feat"}}, [name]
                self.write()
                self.assertEqual(self.podium("launch", "S1", code=1).splitlines()[-1], f"refused repo {name!r}: not a plain name")
                self.assertFalse(os.path.exists(escaped))
                self.assertEqual(self.milestone()["stories"][0]["status"], "todo")

    def test_launch_refuses_a_milestone_id_that_is_a_path(self):
        bad = "../../../../escaped"
        self.data["epics"][0]["milestones"][0]["id"] = self.data["active"]["milestone"] = bad
        self.write()
        self.assertEqual(self.podium("launch", "S1", code=1).splitlines()[-1], f"refused id {bad!r}: not 1-32 letters, digits, _ or -")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escaped")))
        self.assertFalse(os.path.exists(f"{self.main}-S1"))

    def test_backfill_refuses_a_sha_that_is_a_git_option(self):
        target = os.path.join(self.tmp, "written")
        self.data["epics"][0]["milestones"][0]["stories"][0]["commits"] = [{"sha": f"--output={target}", "subject": "s"}]
        self.write()
        self.assertEqual(self.podium("backfill", code=1).splitlines()[-1], f"refused sha '--output={target}': not a commit sha")
        self.assertFalse(os.path.exists(target))

    def test_merge_refuses_a_branch_that_is_a_git_option(self):
        self.data["epics"][0]["milestones"][0]["branch"] = "--orphan=wiped"
        self.write()
        commit(self.story_branch("S1"), "s.txt", "feat: one")
        self.assertEqual(self.podium("merge", "S1", code=1).splitlines()[-1], "refused branch '--orphan=wiped': not a branch name")
        self.assertEqual(git(self.main, "rev-parse", "--abbrev-ref", "HEAD"), "master")
        self.assertTrue(os.path.exists(os.path.join(self.main, "a.txt")))

    def test_prs_refuses_a_pr_number_that_is_not_a_number(self):
        log = os.path.join(self.tmp, "gh.log")
        self.fake("gh", f'echo "$@" >> {log}\n')
        self.data["epics"][0]["milestones"][0]["pr"] = {"number": "--web", "state": "open"}
        self.write()
        self.assertEqual(self.podium("prs", code=1).strip(), "M1 #--web error: not a PR number: '--web'")
        self.assertFalse(os.path.exists(log))

    def test_launch_refuses_a_model_that_is_an_option(self):
        self.data["dispatcher"] = "paseo"
        self.data["epics"][0]["milestones"][0]["stories"][0]["model"] = "--help/x"
        self.write()
        self.assertEqual(self.podium("launch", "S1").strip(), "FAILED S1 model '--help/x': not a model name")
        self.assertFalse(os.path.exists(f"{self.main}-S1"))
        self.assertEqual(self.milestone()["stories"][0]["status"], "todo")

    def test_land_archives_no_paseo_id_that_is_an_option(self):
        log = os.path.join(self.tmp, "paseo.log")
        os.environ["PODIUM_PASEO"] = self.fake("paseo", f'echo "$@" >> {log}\n')
        self.data["epics"][0]["milestones"][0]["stories"][0].update(status="done", agent={"backend": "paseo", "workspace": "--all"})
        self.write()
        self.assertEqual(self.podium("land", "S1").splitlines(), ["LANDED S1", "KEPT S1 paseo --all: not a Paseo id"])
        self.assertFalse(os.path.exists(log))

    def test_handoff_quotes_a_branch_the_shell_would_run(self):
        branch = "feat;touch${IFS}ran"
        self.data["epics"][0]["milestones"][0]["branch"] = branch
        self.write()
        text = self.ext().prompt(Podium(self.run_dir), "handoff", "S1")
        self.assertIn(f"\ngit -C {self.main} worktree add -b story/S1 {self.main}-S1 'feat;touch${{IFS}}ran'\n", text)


class Prompts(Run):
    def test_assign_is_the_story_prompt_and_plan_the_slash_command(self):
        p, ext = Podium(self.run_dir), self.ext()
        assign = ext.prompt(p, "assign", "S1")
        self.assertTrue(assign.startswith("You build one story of an epic, alone, in this worktree, on branch story/S1:"))
        self.assertNotIn("worktree add", assign)
        self.assertEqual(ext.prompt(p, "plan", "M2"), "/orchestrate-deep-plans M2")

    def test_an_unknown_story_or_kind_has_no_prompt(self):
        p, ext = Podium(self.run_dir), self.ext()
        self.assertIsNone(ext.prompt(p, "assign", "M1/S9"))
        self.assertIsNone(ext.prompt(p, "nope", "S1"))

    def test_the_extension_adds_only_verbs_the_core_lacks(self):
        self.assertEqual(sorted(extension.commands(self.ext())),
                         ["approve", "backfill", "breakdown", "brief", "commits", "dispatcher", "handoff", "land", "launch", "merge",
                          "peek", "prs", "turn"])
        self.assertIn("\n    merge\n        Merge story/<id> into its milestone's branch", self.podium("help"))


def load_extension():
    spec = importlib.util.spec_from_file_location("podium_ext_under_test", EXT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SelfUpdate(unittest.TestCase):
    """self_update on a temp clone of a bare "skills repo" holding skill/podium_ext.py, with a stub `podium`."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        os.environ.update(GIT_ENV)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.clone = os.path.join(self.tmp, "skills")
        self.other = os.path.join(self.tmp, "other")
        git(self.tmp, "init", "-q", "--bare", "-b", "main", self.origin)
        git(self.tmp, "clone", "-q", self.origin, self.clone)
        os.makedirs(os.path.join(self.clone, "skill"))
        shutil.copy(EXT, os.path.join(self.clone, "skill", "podium_ext.py"))
        git(self.clone, "add", ".")
        git(self.clone, "commit", "-q", "-m", "init")
        git(self.clone, "push", "-q", "origin", "main")
        git(self.clone, "remote", "set-head", "origin", "main")
        git(self.tmp, "clone", "-q", self.origin, self.other)
        self.ext = load_extension()
        env = unittest.mock.patch.dict(os.environ, {"PODIUM_EXTENSION_FILE": os.path.join(self.clone, "skill", "podium_ext.py")})
        env.start()
        self.addCleanup(env.stop)
        self.stub = os.path.join(self.tmp, "podium-stub.py")
        self.stub_lines([])
        self.ext.PODIUM = [sys.executable, self.stub]
        self.stamp = os.path.join(self.tmp, "update.json")
        patch = unittest.mock.patch.object(human, "HUMAN_FILE", os.path.join(self.tmp, "human.json"))
        patch.start()
        self.addCleanup(patch.stop)

    def stub_lines(self, lines, code=0):
        with open(self.stub, "w") as f:
            f.write(f"import sys\nsys.stdout.write({''.join(l + chr(10) for l in lines)!r})\nsys.exit({code})\n")

    def push_upstream(self):
        commit(self.other, "new.txt", "upstream")
        git(self.other, "push", "-q", "origin", "main")

    def update(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.ext.self_update(None)
        return out.getvalue().splitlines()

    def test_behind_updates_and_asks_for_reload(self):
        self.push_upstream()
        old = git(self.clone, "rev-parse", "HEAD")
        lines = self.update()
        new = git(self.clone, "rev-parse", "HEAD")
        self.assertEqual(lines, [f"UPDATED skills {old[:7]}\u2192{new[:7]}", "RELOAD skills"])
        self.assertNotEqual(old, new)

    def test_current_is_silent(self):
        self.assertEqual(self.update(), [])

    def test_dirty_skill_folder_is_skipped(self):
        self.push_upstream()
        with open(os.path.join(self.clone, "skill", "podium_ext.py"), "a") as f:
            f.write("# local\n")
        self.assertEqual(self.update(), ["SKIP skills folder has changes"])

    def test_other_branch_is_skipped(self):
        self.push_upstream()
        git(self.clone, "checkout", "-q", "-b", "work")
        self.assertEqual(self.update(), ["SKIP skills on work, not main"])

    def test_diverged_warns(self):
        self.push_upstream()
        commit(self.clone, "mine.txt", "local")
        lines = self.update()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("WARN skills "), lines)

    def test_throttled_is_silent_and_force_of_time_checks_again(self):
        self.push_upstream()
        self.assertEqual(len(self.update()), 2)
        self.push_upstream_again()
        self.assertEqual(self.update(), [])
        key = f"skills:{self.clone}"
        with open(self.stamp) as f:
            stamps = json.load(f)
        self.assertIn(key, stamps)
        stamps[key]["at"] = (datetime.now(timezone.utc) - timedelta(seconds=self.ext.UPDATE_EVERY + 60)).isoformat()
        with open(self.stamp, "w") as f:
            json.dump(stamps, f)
        self.assertEqual(len(self.update()), 2)

    def test_the_stamp_keeps_the_tools_key(self):
        with open(self.stamp, "w") as f:
            json.dump({"podium": {"at": "2026-01-01T00:00:00+00:00"}}, f)
        self.update()
        with open(self.stamp) as f:
            stamps = json.load(f)
        self.assertEqual(stamps["podium"], {"at": "2026-01-01T00:00:00+00:00"})
        self.assertIn(f"skills:{self.clone}", stamps)

    def push_upstream_again(self):
        commit(self.other, "again.txt", "again")
        git(self.other, "push", "-q", "origin", "main")

    def test_the_tools_lines_pass_through(self):
        self.stub_lines(["UPDATED podium abc1234\u2192def5678", "RESTART server"])
        self.assertEqual(self.update(), ["UPDATED podium abc1234\u2192def5678", "RESTART server"])

    def test_an_older_tool_without_self_update_is_skipped_silently(self):
        with open(self.stub, "w") as f:
            f.write("import sys\nprint(\"podium: unknown command 'self-update'\", file=sys.stderr)\nsys.exit(2)\n")
        self.assertEqual(self.update(), [])

    def test_a_missing_tool_never_fails(self):
        self.ext.PODIUM = [os.path.join(self.tmp, "absent")]
        self.assertTrue(self.update()[0].startswith("WARN podium"))



if __name__ == "__main__":
    unittest.main()
