"""Offline tests for daily_agent.py (stdlib unittest; no network, no real API keys)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import daily_agent as da  # noqa: E402


class FakeResp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class RetryTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(da, "sleep", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def test_transient_then_success(self):
        seq = [FakeResp(503), FakeResp(429), FakeResp(200, {"ok": 1})]
        with mock.patch.object(da.requests, "request", side_effect=seq) as m:
            self.assertEqual(da.request_with_retry("GET", "http://x").json(), {"ok": 1})
            self.assertEqual(m.call_count, 3)

    def test_permanent_errors_not_retried(self):
        for status in (400, 401, 402, 403, 404):
            with mock.patch.object(da.requests, "request", return_value=FakeResp(status)) as m:
                with self.assertRaises(da.PermanentError):
                    da.request_with_retry("GET", "http://x")
                self.assertEqual(m.call_count, 1, status)

    def test_github_rate_limit_403_is_transient(self):
        seq = [FakeResp(403, {"message": "API rate limit exceeded"}), FakeResp(200, {"ok": 1})]
        with mock.patch.object(da.requests, "request", side_effect=seq):
            self.assertEqual(da.request_with_retry("GET", "http://x").json(), {"ok": 1})

    def test_retries_are_bounded(self):
        with mock.patch.object(da.requests, "request", return_value=FakeResp(502)) as m:
            with self.assertRaises(da.TransientError):
                da.request_with_retry("GET", "http://x", retries=3)
            self.assertEqual(m.call_count, 4)

    def test_timeout_is_transient(self):
        with mock.patch.object(da.requests, "request", side_effect=da.requests.Timeout()):
            with self.assertRaises(da.TransientError):
                da.request_with_retry("GET", "http://x", retries=1)


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.validate = lambda o: None

    def test_fallback_after_permanent_error(self):
        def bad(s, p):
            raise da.PermanentError("HTTP 402: insufficient credits")
        good = lambda s, p: '```json\n{"a": 1}\n```'
        llm = da.LLM([("openrouter", bad), ("gemini", good)])
        self.assertEqual(llm.ask_json("s", "p", self.validate), {"a": 1})
        self.assertEqual(llm.used, "gemini")
        self.assertIn("openrouter", llm.dead)
        calls = []
        llm.providers[0] = ("openrouter", lambda s, p: calls.append(1))
        llm.ask_json("s", "p", self.validate)  # dead provider must not be called again
        self.assertEqual(calls, [])

    def test_all_fail_message_has_no_secret(self):
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-or-SUPERSECRET123"}):
            def bad(s, p):
                raise da.PermanentError("HTTP 401 bad key sk-or-SUPERSECRET123")
            llm = da.LLM([("openrouter", bad)])
            with self.assertRaises(da.AllProvidersFailed) as cm:
                llm.ask_json("s", "p", self.validate)
            self.assertNotIn("SUPERSECRET", str(cm.exception))

    def test_malformed_json_gets_one_repair_attempt(self):
        replies = iter(["not json", '{"ok": true}'])
        llm = da.LLM([("p", lambda s, p: next(replies))])
        self.assertEqual(llm.ask_json("s", "p", self.validate), {"ok": True})

    def test_schema_violation_falls_through(self):
        def validate(o):
            if "need" not in o:
                raise ValueError("missing need")
        llm = da.LLM([("a", lambda s, p: '{"x": 1}'), ("b", lambda s, p: '{"need": 1}')])
        self.assertEqual(llm.ask_json("s", "p", validate), {"need": 1})

    def test_prompt_is_capped(self):
        seen = []
        llm = da.LLM([("a", lambda s, p: seen.append(len(p)) or "{}")])
        llm.ask_json("s", "x" * (da.MAX_PROMPT_CHARS * 3), self.validate)
        self.assertLess(seen[0], da.MAX_PROMPT_CHARS + 50)

    def test_no_providers(self):
        with self.assertRaises(da.AllProvidersFailed):
            da.LLM([]).ask_json("s", "p", self.validate)



class ProviderConfigTests(unittest.TestCase):
    def test_gemini_falls_back_to_next_model_after_503(self):
        with mock.patch.dict(os.environ, {
            "GEMINI_API_KEY": "test-key",
        }, clear=True):
            urls = []

            def fake_request(method, url, **kwargs):
                urls.append(url)
                if "gemini-3.8-flash" in url:
                    raise da.TransientError("HTTP 503")
                return FakeResp(body={"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]})

            with mock.patch.object(da, "request_with_retry", side_effect=fake_request):
                self.assertEqual(da.call_gemini("system", "prompt"), '{"ok":true}')
            self.assertEqual(len(urls), 2)
            self.assertIn("gemini-3.6-flash", urls[1])

    def test_gemini_is_prioritized_over_openrouter(self):
        with mock.patch.dict(os.environ, {
            "GEMINI_API_KEY": "gemini-key",
            "OPENROUTER_API_KEY": "openrouter-key",
        }, clear=True):
            providers = da.LLM().providers
        self.assertEqual([name for name, _ in providers], ["gemini", "openrouter"])

    def test_openrouter_defaults_when_model_variable_is_empty(self):
            captured = {}

            def fake_request(*args, **kwargs):
                captured.update(kwargs)
                return FakeResp(body={"choices": [{"message": {"content": "{}"}}]})

            with mock.patch.object(da, "request_with_retry", side_effect=fake_request):
                self.assertEqual(da.call_openrouter("system", "prompt"), "{}")
            self.assertEqual(captured["json"]["model"], "openrouter/auto")

    def test_gemini_defaults_when_model_variable_is_empty(self):
            captured = {}

            def fake_request(*args, **kwargs):
                captured["url"] = args[1]
                return FakeResp(body={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

            with mock.patch.object(da, "request_with_retry", side_effect=fake_request):
                self.assertEqual(da.call_gemini("system", "prompt"), "{}")
            self.assertTrue(captured["url"].endswith("/models/gemini-3.8-flash:generateContent"))


class FilterTests(unittest.TestCase):
    repo = {"stargazers_count": 500, "pushed_at": da.now().isoformat(), "size": 1000}
    item = {"body": "x" * 200, "labels": [{"name": "bug"}]}

    def test_good_candidate_passes(self):
        self.assertIsNone(da.static_reject(self.item, self.repo))

    def test_rejections(self):
        cases = [
            ({**self.item, "pull_request": {}}, self.repo, "pull request"),
            ({**self.item, "body": "short"}, self.repo, "vague"),
            ({**self.item, "assignee": {"login": "x"}}, self.repo, "assigned"),
            ({**self.item, "labels": [{"name": "wontfix"}]}, self.repo, "label"),
            (self.item, {**self.repo, "archived": True}, "archived"),
            (self.item, {**self.repo, "pushed_at": "2020-01-01T00:00:00Z"}, "inactive"),
        ]
        for item, repo, word in cases:
            reason = da.static_reject(item, repo)
            self.assertTrue(reason and word in reason, (word, reason))

    def test_star_threshold_is_configurable_and_defaults_allow_small_repos(self):
        small_repo = {**self.repo, "stargazers_count": 1}
        with mock.patch.object(da, "MIN_STARS", 0):
            self.assertIsNone(da.static_reject(self.item, small_repo))
        with mock.patch.object(da, "MIN_STARS", 10):
            self.assertIn("stars", da.static_reject(self.item, small_repo))

    def test_claimed_in_comments(self):
        self.assertIsNotNone(da.comment_reject([{"body": "I'll take this one!"}]))
        self.assertIsNone(da.comment_reject([{"body": "I can reproduce this on 3.12"}]))

    def test_ai_policy_regex(self):
        self.assertTrue(da.AI_BAN_RE.search("We do not accept AI-generated pull requests."))
        self.assertFalse(da.AI_BAN_RE.search("Please run the tests. Thanks, mail us again."))

    def test_secret_scan(self):
        self.assertIsNotNone(da.scan_secrets("+key = 'AKIAABCDEFGHIJKLMNOP'"))
        self.assertIsNone(da.scan_secrets("+print('hello')"))

    def test_queries_cover_languages_and_docs(self):
        qs = " ".join(da.build_queries("2026-01-01"))
        for lang in ("python", "javascript", "typescript", "shell", "documentation"):
            self.assertIn(lang, qs)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        (self.d / "a.py").write_text("x = 1\nprint(x)\nprint(x)\n")
        (self.d / "b.py").write_text("y = 2\n")
        self.tracked = {"a.py", "b.py"}

    def plan(self, **kw):
        return {"edits": [{"path": "b.py", "old": "y = 2", "new": "y = 3", **kw}]}

    def test_valid_edit(self):
        self.assertEqual(da.apply_plan(self.d, self.plan(), self.tracked), ["b.py"])
        self.assertEqual((self.d / "b.py").read_text(), "y = 3\n")

    def test_ambiguous_match_rejected(self):
        with self.assertRaises(da.PatchError):
            da.apply_plan(self.d, {"edits": [{"path": "a.py", "old": "print(x)", "new": "print(x + 1)"}]}, self.tracked)

    def test_missing_old_rejected(self):
        with self.assertRaises(da.PatchError):
            da.apply_plan(self.d, self.plan(old="nope"), self.tracked)

    def test_traversal_and_workflow_paths_rejected(self):
        for path in ("../evil.py", ".github/workflows/ci.yml", "/etc/passwd"):
            with self.assertRaises(da.PatchError):
                da.apply_plan(self.d, {"edits": [{"path": path, "old": "a", "new": "b"}]}, self.tracked | {path})

    def test_cosmetic_edit_rejected(self):
        with self.assertRaises(da.PatchError):
            da.apply_plan(self.d, self.plan(new="y=2"), self.tracked)

    def test_new_files_only_for_tests(self):
        with self.assertRaises(da.PatchError):
            da.apply_plan(self.d, {"new_files": [{"path": "feature.py", "content": "pass"}]}, self.tracked)
        ok = da.apply_plan(self.d, {"new_files": [{"path": "tests/test_new.py", "content": "pass\n"}]}, self.tracked)
        self.assertEqual(ok, ["tests/test_new.py"])

    def test_empty_plan_rejected(self):
        with self.assertRaises(da.PatchError):
            da.apply_plan(self.d, {}, self.tracked)


class DiscoveryRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(da, "STATE_DIR", Path(self.tmp.name) / "state")
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(da, "sleep", lambda seconds: None)
        p.start()
        self.addCleanup(p.stop)

    def test_run_collects_opportunities_without_ai(self):
        item = {"html_url": "https://github.com/acme/project/issues/12", "repository_url": "https://api.github.com/repos/acme/project",
                "number": 12, "title": "Fix a beginner-friendly bug", "body": "A detailed issue description. " * 8,
                "labels": [{"name": "good first issue"}, {"name": "bug"}], "comments": 0, "updated_at": "2026-11-17T10:00:00Z"}
        class FakeGH:
            def get(self, path, **params):
                self.last_path = path
                return {"stargazers_count": 1200, "language": "Python", "pushed_at": da.now().isoformat(), "size": 100}
        agent = da.Agent(FakeGH(), None, da.Report(), None, False)
        agent.discover = lambda: [item]
        with mock.patch.object(da.LLM, "ask_json", side_effect=AssertionError("AI must not run")):
            report = agent.run()
        self.assertEqual(report.status, "opportunities_found")
        self.assertEqual(len(report.opportunities), 1)
        self.assertEqual(report.opportunities[0]["repository"], "acme/project")
        self.assertEqual(report.opportunities[0]["language"], "Python")
        self.assertEqual(report.ai_attempts, 0)

    def test_run_reports_empty_discovery(self):
        class FakeGH:
            def get(self, path, **params):
                return {"stargazers_count": 100, "language": "Python", "pushed_at": da.now().isoformat(), "size": 100}
        agent = da.Agent(FakeGH(), None, da.Report(), None, False)
        agent.discover = lambda: []
        report = agent.run()
        self.assertEqual(report.status, "no_opportunities")
        self.assertEqual(report.opportunities, [])
class EndToEndPatchGateTests(unittest.TestCase):
    """Real git repo + real test command; GitHub and the LLM are faked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.upstream = base / "upstream"
        self.upstream.mkdir()
        (self.upstream / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.upstream / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n\n\nif __name__ == '__main__':\n    unittest.main()\n")
        (self.upstream / "Makefile").write_text("test:\n\tpython3 -m unittest discover -q\n")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
            subprocess.run(cmd, cwd=self.upstream, check=True)
        for name, val in (("OUT_DIR", base / "out"), ("STATE_DIR", base / "st")):
            p = mock.patch.object(da, name, val)
            p.start()
            self.addCleanup(p.stop)
        real_run = da.run

        def fake_run(cmd, *a, **k):  # redirect the clone to the local fixture repo
            if isinstance(cmd, list) and cmd[:3] == ["git", "clone", "--depth"]:
                cmd = ["git", "clone", "-q", str(self.upstream), cmd[-1]]
            return real_run(cmd, *a, **k)

        p = mock.patch.object(da, "run", fake_run)
        p.start()
        self.addCleanup(p.stop)
        # pytest cannot be pip-installed offline, so use the fixture's `make test` target
        p = mock.patch.object(da, "detect_tests",
                              lambda d, f: {"name": "make test", "setup": [], "cmd": "make test"}
                              if (d / "Makefile").exists() else None)
        p.start()
        self.addCleanup(p.stop)

    def agent(self, plan, pr_spy):
        s1 = {"feasible": True, "reason": "", "files": ["calc.py"]}
        replies = iter([s1, plan])

        class FakeLLM(da.LLM):
            def ask_json(s, system, prompt, validate):
                s.used = "fake"
                return next(replies)

        a = da.Agent(None, FakeLLM([("fake", None)]), da.Report(), pat="x", dry_run=False)
        a.open_pr = lambda *args, **kw: pr_spy.append(1) or "https://github.com/o/r/pull/1"
        a.prepare_env = lambda work, repo_dir: sys.executable
        return a

    def item(self):
        return {"html_url": "https://github.com/o/r/issues/7", "number": 7, "title": "add is wrong", "body": "b" * 100}

    def test_failing_tests_block_pr(self):
        spy = []
        bad_plan = {"feasible": True, "summary": "oops", "edits": [
            {"path": "calc.py", "old": "return a + b", "new": "return a - b"}]}
        a = self.agent(bad_plan, spy)
        with self.assertRaises(da.Reject) as cm:
            a._attempt("o", "r", {"default_branch": "main"}, self.item(), Path(self.tmp.name) / "w1")
        self.assertIn("tests failed after patch", str(cm.exception))
        self.assertEqual(spy, [])
        self.assertEqual(a.report.test_failures, 1)

    def test_passing_tests_allow_pr(self):
        spy = []
        good_plan = {"feasible": True, "summary": "handle None", "edits": [
            {"path": "calc.py", "old": "return a + b", "new": "return (a or 0) + (b or 0)"}]}
        a = self.agent(good_plan, spy)
        a._attempt("o", "r", {"default_branch": "main"}, self.item(), Path(self.tmp.name) / "w2")
        self.assertEqual(spy, [1])
        self.assertEqual(a.report.status, "pr_created")
        self.assertTrue(a.report.tests[-1]["passed"])
        self.assertTrue((da.OUT_DIR / "patch.diff").read_text().startswith("diff --git"))

    def test_code_change_without_tests_rejected(self):
        (self.upstream / "Makefile").unlink()
        (self.upstream / "test_calc.py").unlink()
        subprocess.run(["git", "add", "-A"], cwd=self.upstream, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "rm"],
                       cwd=self.upstream, check=True)
        spy = []
        plan = {"feasible": True, "summary": "x", "edits": [
            {"path": "calc.py", "old": "return a + b", "new": "return b + a + 0"}]}
        a = self.agent(plan, spy)
        with self.assertRaises(da.Reject) as cm:
            a._attempt("o", "r", {"default_branch": "main"}, self.item(), Path(self.tmp.name) / "w3")
        self.assertIn("no runnable test command", str(cm.exception))
        self.assertEqual(spy, [])

    def test_dry_run_never_opens_pr(self):
        spy = []
        good_plan = {"feasible": True, "summary": "s", "edits": [
            {"path": "calc.py", "old": "return a + b", "new": "return (a or 0) + (b or 0)"}]}
        a = self.agent(good_plan, spy)
        a.dry_run = True
        a._attempt("o", "r", {"default_branch": "main"}, self.item(), Path(self.tmp.name) / "w4")
        self.assertEqual(spy, [])
        self.assertEqual(a.report.status, "validated_no_pr")


class DetectTests(unittest.TestCase):
    def test_detection(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            self.assertIsNone(da.detect_tests(d, ["README.md", "a.sh"]))
            self.assertEqual(da.detect_tests(d, ["tests/test_a.py"])["name"], "pytest")
            (d / "Makefile").write_text("test:\n\techo ok\n")
            self.assertEqual(da.detect_tests(d, [])["name"], "make test")
            (d / "package.json").write_text('{"scripts": {"test": "echo \\"Error: no test specified\\" && exit 1"}}')
            self.assertEqual(da.detect_tests(d, [])["name"], "make test")  # npm default stub ignored
            (d / "package.json").write_text('{"scripts": {"test": "jest"}}')
            self.assertEqual(da.detect_tests(d, [])["name"], "npm test")


class ReportTests(unittest.TestCase):
    def test_telegram_text_contents_and_redaction(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123456:SECRETTOKEN"}):
            rep = {"status": "opportunities_found", "summary": "found", "discovered": 30, "examined": 12, "opportunities": [{"title": "Fix parser bug", "repository": "acme/parser", "stars": 500, "language": "Python", "labels": ["good first issue"], "body": "A clear bug", "url": "https://github.com/acme/parser/issues/3"}],
                   "ai_attempts": 2, "tests": [], "provider": "gemini", "error": "boom 123456:SECRETTOKEN",
                   "rejections": [{"url": "u", "reason": "vague: issue body too short"}] * 3}
            text = da.format_report(rep, "https://github.com/x/y/actions/runs/1")
        self.assertIn("Daily GitHub Opportunity Finder", text)
        self.assertIn("Fix parser bug", text)
        self.assertIn("acme/parser", text)
        self.assertIn("https://github.com/acme/parser/issues/3", text)
        self.assertIn("runs/1", text)
        self.assertNotIn("SECRETTOKEN", text)

    def test_missing_report_is_reported_as_crash(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(da, "OUT_DIR", Path(t)), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok-123456", "TELEGRAM_CHAT_ID": "1",
                                             "AGENT_OUTCOME": "failure"}), \
                mock.patch.object(da, "request_with_retry") as m:
            self.assertEqual(da.cmd_telegram(), 0)
            sent = m.call_args.kwargs["json"]["text"]
        self.assertIn("crashed", sent)
        self.assertIn("failure", sent)

    def test_telegram_failure_is_not_silent(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(da, "OUT_DIR", Path(t)), \
                mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "tok-123456", "TELEGRAM_CHAT_ID": "1"}), \
                mock.patch.object(da, "request_with_retry", side_effect=da.PermanentError("HTTP 401")):
            self.assertEqual(da.cmd_telegram(), 1)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        import yaml
        path = Path(__file__).parent.parent / ".github" / "workflows" / "daily-open-source-ai-agent.yml"
        self.wf = yaml.safe_load(path.read_text())
        self.on = self.wf.get("on", self.wf.get(True))  # PyYAML parses bare `on` as True

    def test_triggers(self):
        self.assertIn("workflow_dispatch", self.on)
        cron = self.on["schedule"][0]["cron"]
        m, h, dom, mon, dow = cron.split()
        self.assertEqual((dom, mon, dow), ("*", "*", "*"))  # every day
        self.assertTrue(0 <= int(m) < 60 and 0 <= int(h) < 24)

    def test_safety_settings(self):
        self.assertEqual(self.wf["permissions"]["contents"], "read")
        self.assertFalse(self.wf["concurrency"]["cancel-in-progress"])
        job = self.wf["jobs"]["agent"]
        self.assertLessEqual(job["timeout-minutes"], 60)
        steps = {s.get("name"): s for s in job["steps"]}
        self.assertEqual(steps["Telegram report"]["if"], "always()")
        self.assertTrue(steps["Discover GitHub opportunities"]["continue-on-error"])
        env = steps["Discover GitHub opportunities"]["env"]
        self.assertNotIn("GEMINI_API_KEY", env)
        self.assertNotIn("OPENROUTER_API_KEY", env)
        self.assertEqual(env["AGENT_MIN_STARS"], "${{ vars.AGENT_MIN_STARS || '0' }}")


if __name__ == "__main__":
    unittest.main(verbosity=2)