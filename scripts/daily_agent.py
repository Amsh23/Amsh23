#!/usr/bin/env python3
"""Daily open-source contribution agent.

Usage:
    python scripts/daily_agent.py run        # discover -> evaluate -> patch -> test -> PR
    python scripts/daily_agent.py telegram   # send out/report.json to Telegram

Design rules
  * Every candidate is evaluated independently; a rejection never stops the run.
  * Every rejection reason is recorded and reported, so "no suitable issue"
    always comes with the reasons.
  * A PR is opened only after the upstream test command passes (and passed
    before the patch too). Code changes without any runnable tests are rejected.
  * Upstream code runs with a scrubbed environment (no secrets).
  * Secrets are redacted from every message that is logged or reported.
"""
from __future__ import annotations

import argparse
import base64
import difflib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests

API = "https://api.github.com"
OUT_DIR = Path(os.environ.get("AGENT_OUT_DIR", "out"))
STATE_DIR = Path(os.environ.get("AGENT_STATE_DIR", ".agent_state"))

TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_PROMPT_CHARS = int(os.environ.get("AGENT_MAX_PROMPT_CHARS", "24000"))
MAX_CANDIDATES = int(os.environ.get("AGENT_MAX_CANDIDATES", "40"))  # cheap checks, no AI
MAX_AI_ATTEMPTS = int(os.environ.get("AGENT_MAX_AI_ATTEMPTS", "5"))  # candidates that reach the AI stage
MIN_STARS = int((os.environ.get("AGENT_MIN_STARS") or "0").strip() or "0")
SEEN_TTL_DAYS = 30
TEST_TIMEOUT = int(os.environ.get("AGENT_TEST_TIMEOUT", "900"))

SECRET_ENV = ["GH_PAT", "GITHUB_TOKEN", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN"]
BAD_LABELS = {"wontfix", "won't fix", "duplicate", "invalid", "question", "discussion", "stale",
              "needs more info", "needs-info", "blocked", "on hold", "rfc", "proposal"}
CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".sh", ".bash", ".go", ".rs", ".java",
             ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".swift"}
DOC_EXTS = {".md", ".rst", ".txt", ".adoc"}
SKIP_PATH_RE = re.compile(
    r"(^|/)(node_modules|vendor|dist|build|\.git|\.github/workflows)(/|$)|"
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|Pipfile\.lock)$|"
    r"\.(png|jpe?g|gif|svg|ico|pdf|zip|gz|tar|woff2?|ttf|eot|mp[34]|bin|exe|so|dll|min\.js)$", re.I)
CLAIM_RE = re.compile(
    r"\b(i['’]?m (working|on it|taking)|i['’]?ll (take|work on|fix|submit|open)|i will (take|work on|fix|submit)|"
    r"working on (this|it)|assign (this )?to me|can i (work|take|pick)|i['’]?d like to (work|take)|"
    r"already (fixed|resolved|being worked)|duplicate of #|fixed in #|has been fixed)\b", re.I)
AI_BAN_RE = re.compile(
    r"\b(no|not|don['’]?t|do not|never|prohibit\w*|ban\w*|forbid\w*|disallow\w*|reject\w*)\b[^.\n]{0,60}"
    r"\b(ai|llm|llms|chatgpt|copilot|ai-generated|machine[- ]generated)\b", re.I)
SECRET_PATTERNS = [r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}",
                   r"sk-[A-Za-z0-9_-]{20,}", r"AIza[0-9A-Za-z_-]{35}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"]


# --------------------------------------------------------------------------- errors / utils
class TransientError(Exception):
    """Temporary failure (retries exhausted)."""


class PermanentError(Exception):
    """Failure that retrying cannot fix (auth, config, credits, 4xx)."""


class AllProvidersFailed(Exception):
    pass


class Reject(Exception):
    """Candidate is unsuitable; the run continues with the next one."""


class PatchError(Reject):
    pass


def redact(text: Any) -> str:
    text = str(text)
    for name in SECRET_ENV:
        val = os.environ.get(name)
        if val and len(val) >= 6:
            text = text.replace(val, "***")
    return re.sub(r"(?i)(authorization: *(basic|bearer) +)\S+", r"\1***", text)


def log(msg: str) -> None:
    print(redact(msg), flush=True)


def now() -> datetime:
    return datetime.now(timezone.utc)


def sleep(seconds: float) -> None:  # separate function so tests can patch it
    time.sleep(seconds)


def request_with_retry(method: str, url: str, *, retries: int = 4, timeout: int = 60, **kw: Any) -> requests.Response:
    """HTTP with exponential backoff. Transient -> retry; everything else -> PermanentError."""
    last: Exception = TransientError("no attempt made")
    for attempt in range(retries + 1):
        retry_after = 0.0
        try:
            resp = requests.request(method, url, timeout=timeout, **kw)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = TransientError(f"network error: {type(exc).__name__}")
        else:
            if resp.status_code < 400:
                return resp
            body = resp.text[:300]
            rate_limited = resp.status_code == 403 and "rate limit" in body.lower()
            if resp.status_code in TRANSIENT_STATUS or rate_limited:
                last = TransientError(f"HTTP {resp.status_code}")
                try:
                    retry_after = float(resp.headers.get("Retry-After", 0))
                except ValueError:
                    retry_after = 0.0
            else:  # 400/401/402/403/404/422 ... retrying cannot help
                raise PermanentError(f"HTTP {resp.status_code}: {redact(body)}")
        if attempt < retries:
            delay = min(60.0, 2.0 ** attempt) + random.random()
            sleep(min(max(delay, retry_after), 120.0))
    raise last


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found")
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(obj, dict):
        raise ValueError("JSON root is not an object")
    return obj


# --------------------------------------------------------------------------- AI providers
def call_openrouter(system: str, prompt: str) -> str:
    key = os.environ["OPENROUTER_API_KEY"]
    resp = request_with_retry(
        "POST", "https://openrouter.ai/api/v1/chat/completions", timeout=120, retries=3,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": (os.environ.get("OPENROUTER_MODEL") or "").strip() or "openrouter/auto", "temperature": 0.2,
              "max_tokens": 6000, "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": prompt}]})
    data = resp.json()
    if "error" in data:  # OpenRouter can return HTTP 200 with an error body
        raise PermanentError(f"openrouter error: {redact(json.dumps(data['error'])[:300])}")
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentError("openrouter: unexpected response shape") from exc


def call_gemini(system: str, prompt: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    primary = (os.environ.get("GEMINI_MODEL") or "").strip() or "gemini-3.8-flash"
    fallback_text = os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.1-flash-lite"
    )
    models = list(dict.fromkeys([primary] + [m.strip() for m in fallback_text.split(",") if m.strip()]))
    failures = []
    for model in models:
        try:
            resp = request_with_retry(
                "POST", f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                timeout=120, retries=3, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                json={"systemInstruction": {"parts": [{"text": system}]},
                      "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json",
                                           "maxOutputTokens": 8000}})
            try:
                return "".join(p.get("text", "") for p in resp.json()["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError, TypeError) as exc:
                raise PermanentError(f"gemini {model}: unexpected response shape (blocked or empty)") from exc
        except TransientError as exc:
            failures.append(f"{model}: {redact(exc)}")
            log(f"Gemini model {model} unavailable; trying next configured model")
    raise TransientError("all Gemini models unavailable after retries: " + "; ".join(failures))


class LLM:
    def __init__(self, providers: list[tuple[str, Callable[[str, str], str]]] | None = None):
        if providers is None:
            providers = []
            # Prefer Gemini's free tier; only use OpenRouter if Gemini is unavailable.
            if os.environ.get("GEMINI_API_KEY"):
                providers.append(("gemini", call_gemini))
            if os.environ.get("OPENROUTER_API_KEY"):
                providers.append(("openrouter", call_openrouter))
        self.providers = providers
        self.dead: dict[str, str] = {}
        self.used: str | None = None

    def ask_json(self, system: str, prompt: str, validate: Callable[[dict], None]) -> dict:
        if len(prompt) > MAX_PROMPT_CHARS:
            half = MAX_PROMPT_CHARS // 2
            prompt = prompt[:half] + "\n...[truncated]...\n" + prompt[-half:]
        errors: list[str] = []
        for name, fn in self.providers:
            if name in self.dead:
                errors.append(f"{name}: disabled for this run ({self.dead[name]})")
                continue
            attempt_prompt = prompt
            for _ in range(2):  # one repair attempt for malformed JSON
                try:
                    text = fn(system, attempt_prompt)
                except PermanentError as exc:
                    self.dead[name] = redact(exc)
                    errors.append(f"{name}: permanent error: {redact(exc)}")
                    break
                except TransientError as exc:
                    errors.append(f"{name}: transient error after retries: {redact(exc)}")
                    break
                try:
                    obj = parse_json(text)
                    validate(obj)
                    self.used = name
                    return obj
                except ValueError as exc:
                    errors.append(f"{name}: bad model output ({exc})")
                    attempt_prompt = prompt + "\n\nYour previous reply was not valid. Reply with ONLY the JSON object."
        raise AllProvidersFailed("; ".join(redact(e) for e in errors) or "no AI provider configured")


# --------------------------------------------------------------------------- GitHub
class GH:
    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28"}

    def get(self, path: str, **params: Any) -> Any:
        return request_with_retry("GET", API + path, headers=self.headers, params=params or None).json()

    def post(self, path: str, payload: dict) -> Any:
        return request_with_retry("POST", API + path, headers=self.headers, json=payload).json()


def build_queries(since: str) -> list[str]:
    tail = f"is:issue is:open no:assignee comments:<6 updated:>={since} archived:false"
    qs = []
    for lang in ("python", "javascript", "typescript", "shell"):
        qs.append(f'label:"good first issue" language:{lang} {tail}')
        qs.append(f'label:"help wanted" label:bug language:{lang} {tail}')
        qs.append(f'label:bug language:{lang} {tail}')
    qs.append(f'label:documentation {tail}')
    qs.append(f'label:"good first issue" label:documentation {tail}')
    return qs


def load_seen() -> dict[str, dict]:
    path = STATE_DIR / "seen.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    cutoff = now() - timedelta(days=SEEN_TTL_DAYS)
    return {k: v for k, v in data.items() if datetime.fromisoformat(v["ts"]) > cutoff}


def save_seen(seen: dict[str, dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "seen.json").write_text(json.dumps(seen, indent=1))


def static_reject(item: dict, repo: dict) -> str | None:
    """Cheap, deterministic filters. Returns a rejection reason or None."""
    if "pull_request" in item:
        return "is a pull request"
    if repo.get("archived") or repo.get("disabled"):
        return "repository archived/disabled"
    if repo.get("fork"):
        return "repository is a fork"
    if repo.get("stargazers_count", 0) < MIN_STARS:
        return f"repository has fewer than {MIN_STARS} stars"
    pushed = repo.get("pushed_at")
    if pushed and datetime.fromisoformat(pushed.replace("Z", "+00:00")) < now() - timedelta(days=90):
        return "repository inactive for 90+ days"
    if repo.get("size", 0) > 300_000:
        return "repository too large (>300 MB)"
    if item.get("assignee") or item.get("assignees"):
        return "issue already assigned"
    labels = {(l.get("name") if isinstance(l, dict) else str(l)).lower() for l in item.get("labels", [])}
    bad = labels & BAD_LABELS
    if bad:
        return f"unsuitable label: {sorted(bad)[0]}"
    if len((item.get("body") or "").strip()) < 80:
        return "vague: issue body too short"
    return None


def comment_reject(comments: list[dict]) -> str | None:
    for c in comments:
        if CLAIM_RE.search(c.get("body") or ""):
            return "someone already claimed/fixed it in comments"
    return None


# --------------------------------------------------------------------------- local helpers
def run(cmd: list[str] | str, cwd: Path | None = None, timeout: int = 600, scrub: bool = True,
        extra_env: dict | None = None) -> subprocess.CompletedProcess:
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
    env = {k: v for k, v in os.environ.items() if k in keep} if scrub else dict(os.environ)
    env.update({"CI": "1", "GIT_TERMINAL_PROMPT": "0"})
    env.update(extra_env or {})
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str), capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"")
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
        return subprocess.CompletedProcess(cmd, 124, out, f"timeout after {timeout}s")


def tail(text: str, n: int = 1500) -> str:
    return text[-n:] if len(text) > n else text


def rank_files(files: list[str], title: str, limit: int = 400) -> list[str]:
    words = {w.lower() for w in re.findall(r"[A-Za-z_]{4,}", title)}
    files = [f for f in files if not SKIP_PATH_RE.search(f)]
    return sorted(files, key=lambda f: (-sum(w in f.lower() for w in words), f))[:limit]


def apply_plan(repo_dir: Path, plan: dict, tracked: set[str]) -> list[str]:
    """Validate and apply AI-proposed edits. Raises PatchError on anything unsafe."""
    edits, new_files = plan.get("edits") or [], plan.get("new_files") or []
    if not edits and not new_files:
        raise PatchError("AI proposed no changes")
    touched: dict[str, str] = {}
    root = repo_dir.resolve()

    def safe(rel: str) -> Path:
        p = (repo_dir / rel).resolve()
        if root not in p.parents or SKIP_PATH_RE.search(rel) or rel.startswith("/"):
            raise PatchError(f"forbidden path: {rel}")
        return p

    originals: dict[str, str] = {}
    for e in edits:
        rel = str(e.get("path", ""))
        p = safe(rel)
        if rel not in tracked or not p.is_file():
            raise PatchError(f"edit targets untracked/missing file: {rel}")
        text = touched.get(rel) or p.read_text(encoding="utf-8")
        originals.setdefault(rel, text)
        old, new = str(e.get("old", "")), str(e.get("new", ""))
        if not old or old == new or re.sub(r"\s+", "", old) == re.sub(r"\s+", "", new):
            raise PatchError(f"no-op or whitespace-only edit in {rel}")
        if text.count(old) != 1:
            raise PatchError(f"'old' text matches {text.count(old)} times in {rel} (must be exactly 1)")
        touched[rel] = text.replace(old, new)
    for nf in new_files:
        rel = str(nf.get("path", ""))
        p = safe(rel)
        if p.exists():
            raise PatchError(f"new file already exists: {rel}")
        if not re.search(r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)(test_[^/]*|[^/]*_test\.\w+|[^/]*\.(test|spec)\.\w+)$", rel):
            raise PatchError(f"new files are only allowed for tests: {rel}")
        content = str(nf.get("content", ""))
        if len(content) > 20000:
            raise PatchError(f"new test file too large: {rel}")
        originals[rel] = ""
        touched[rel] = content
    if len(touched) > 6:
        raise PatchError("patch touches more than 6 files")
    changed_lines = 0
    for rel, new_text in touched.items():
        diff = difflib.unified_diff(originals[rel].splitlines(), new_text.splitlines(), lineterm="", n=0)
        changed_lines += sum(1 for d in diff if d[:1] in "+-" and d[:3] not in ("+++", "---"))
    if changed_lines > 250:
        raise PatchError(f"patch too large ({changed_lines} changed lines)")
    for rel, new_text in touched.items():
        p = repo_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_text, encoding="utf-8")
    return sorted(touched)


def detect_tests(repo_dir: Path, files: list[str]) -> dict | None:
    pkg = repo_dir / "package.json"
    if pkg.is_file():
        try:
            script = json.loads(pkg.read_text()).get("scripts", {}).get("test", "")
        except ValueError:
            script = ""
        if script and "no test specified" not in script:
            return {"name": "npm test", "setup": ["npm install --no-audit --no-fund"], "cmd": "npm test --silent"}
    def txt(name: str) -> str:
        f = repo_dir / name
        return f.read_text(errors="ignore") if f.is_file() else ""
    pytest_cfg = (repo_dir / "pytest.ini").is_file() or "[pytest]" in txt("tox.ini") \
        or "[tool:pytest]" in txt("setup.cfg") or "[tool.pytest" in txt("pyproject.toml")
    has_tests = any(re.search(r"(^|/)(tests?/.*\.py|test_[^/]*\.py)$", f) for f in files)
    if pytest_cfg or has_tests:
        setup = ["{py} -m pip install -q pytest"]
        if (repo_dir / "pyproject.toml").is_file() or (repo_dir / "setup.py").is_file():
            setup.append("{py} -m pip install -q -e . || true")
        for req in ("requirements-dev.txt", "requirements_dev.txt", "test-requirements.txt", "requirements.txt"):
            if (repo_dir / req).is_file():
                setup.append(f"{{py}} -m pip install -q -r {req} || true")
        return {"name": "pytest", "setup": setup, "cmd": "{py} -m pytest -x -q"}
    if re.search(r"(?m)^test:", txt("Makefile")):
        return {"name": "make test", "setup": [], "cmd": "make test"}
    return None


def syntax_check(repo_dir: Path, rels: list[str]) -> list[str]:
    problems = []
    for rel in rels:
        p, ext = repo_dir / rel, Path(rel).suffix.lower()
        if ext == ".py":
            r = run([sys.executable, "-m", "py_compile", str(p)], scrub=True)
        elif ext == ".json":
            try:
                json.loads(p.read_text())
                continue
            except ValueError as exc:
                problems.append(f"{rel}: invalid JSON ({exc})")
                continue
        elif ext in (".sh", ".bash"):
            r = run(["bash", "-n", str(p)])
        elif ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
            r = run(["node", "--check", str(p)])
        else:
            continue
        if r.returncode != 0:
            problems.append(f"{rel}: syntax error: {tail(r.stderr, 300)}")
    return problems


def scan_secrets(diff_text: str) -> str | None:
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            for pat in SECRET_PATTERNS:
                if re.search(pat, line):
                    return "possible secret in added lines"
    return None


# --------------------------------------------------------------------------- report
@dataclass
class Report:
    status: str = "crashed"
    summary: str = ""
    discovered: int = 0
    examined: int = 0
    opportunities: list[dict] = field(default_factory=list)
    ai_attempts: int = 0
    rejections: list[dict] = field(default_factory=list)
    selected_issue: dict | None = None
    files: list[str] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    provider: str | None = None
    pr_url: str | None = None
    error: str | None = None
    dry_run: bool = False
    test_failures: int = 0
    started: str = field(default_factory=lambda: now().isoformat(timespec="seconds"))

    def reject(self, url: str, reason: str) -> None:
        self.rejections.append({"url": url, "reason": reason})
        log(f"REJECT {url}: {reason}")


# --------------------------------------------------------------------------- agent
class Agent:
    def __init__(self, gh: GH, llm: LLM, report: Report, pat: str | None, dry_run: bool):
        self.gh, self.llm, self.report, self.pat, self.dry_run = gh, llm, report, pat, dry_run
        self.seen = load_seen()

    # ---- discovery
    def discover(self) -> list[dict]:
        since = (now() - timedelta(days=60)).strftime("%Y-%m-%d")
        found: dict[str, dict] = {}
        queries = build_queries(since)
        random.shuffle(queries)
        for q in queries:
            try:
                data = self.gh.get("/search/issues", q=q, sort="updated", order="desc", per_page=30,
                                   page=random.randint(1, 3))
            except (PermanentError, TransientError) as exc:
                log(f"search failed ({redact(exc)}): {q[:60]}")
                continue
            for it in data.get("items", []):
                found.setdefault(it["html_url"], it)
            sleep(2.5)  # search API: 30 req/min
        items = [it for url, it in found.items() if url not in self.seen]
        random.shuffle(items)
        return items

    # ---- candidate pipeline
    def check_linked_prs(self, owner: str, repo: str, number: int) -> None:
        events = self.gh.get(f"/repos/{owner}/{repo}/issues/{number}/timeline", per_page=100)
        for ev in events:
            src = (ev.get("source") or {}).get("issue") or {}
            if ev.get("event") == "cross-referenced" and src.get("pull_request"):
                if src.get("state") == "open" or src["pull_request"].get("merged_at"):
                    raise Reject("a linked pull request already exists")

    def check_policy(self, owner: str, repo: str) -> None:
        try:
            data = self.gh.get(f"/repos/{owner}/{repo}/contents/CONTRIBUTING.md")
            text = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
        except (PermanentError, TransientError, ValueError):
            return
        if AI_BAN_RE.search(text):
            raise Reject("CONTRIBUTING.md appears to restrict AI-assisted contributions")

    def prepare_env(self, work: Path, repo_dir: Path) -> str:
        """Create a venv for Python tests; returns the interpreter path. Tests override this."""
        venv = work / "venv"
        run([sys.executable, "-m", "venv", str(venv)], timeout=120)
        return str(venv / "bin" / "python")

    def run_tests(self, repo_dir: Path, spec: dict, py: str) -> dict:
        for s in spec["setup"]:
            r = run(s.format(py=py), cwd=repo_dir, timeout=TEST_TIMEOUT)
            if r.returncode != 0 and "|| true" not in s:
                return {"cmd": spec["name"], "passed": False, "detail": "setup failed: " + tail(r.stderr or r.stdout, 400)}
        r = run(spec["cmd"].format(py=py), cwd=repo_dir, timeout=TEST_TIMEOUT)
        return {"cmd": spec["name"], "passed": r.returncode == 0,
                "detail": tail((r.stdout + r.stderr).strip(), 600)}

    def process(self, item: dict) -> None:
        """Run one candidate through the full pipeline. Raises Reject if unsuitable."""
        owner, repo = item["repository_url"].rsplit("/", 2)[-2:]
        number, url = item["number"], item["html_url"]
        info = self.gh.get(f"/repos/{owner}/{repo}")
        reason = static_reject(item, info)
        if reason:
            raise Reject(reason)
        reason = comment_reject(self.gh.get(f"/repos/{owner}/{repo}/issues/{number}/comments", per_page=30))
        if reason:
            raise Reject(reason)
        self.check_linked_prs(owner, repo, number)
        self.check_policy(owner, repo)

        if self.report.ai_attempts >= MAX_AI_ATTEMPTS:
            raise StopIteration("AI attempt budget exhausted")
        self.report.ai_attempts += 1
        work = Path(tempfile.mkdtemp(prefix="agent_"))
        try:
            self._attempt(owner, repo, info, item, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _attempt(self, owner: str, repo: str, info: dict, item: dict, work: Path) -> None:
        number, url, title = item["number"], item["html_url"], item["title"]
        repo_dir = work / "repo"
        r = run(["git", "clone", "--depth", "1", f"https://github.com/{owner}/{repo}.git", str(repo_dir)],
                timeout=300)
        if r.returncode != 0:
            raise Reject(f"clone failed: {tail(r.stderr, 200)}")
        files = run(["git", "ls-files"], cwd=repo_dir).stdout.splitlines()
        tracked = set(files)
        body = (item.get("body") or "")[:3000]
        system = "You are a careful senior open-source maintainer. Reply with ONLY one JSON object."

        # stage 1: which files matter, and is the issue actionable at all?
        ranked = rank_files(files, title)
        p1 = (f"Repository: {owner}/{repo}\nIssue #{number}: {title}\n\n{body}\n\nTracked files:\n"
              + "\n".join(ranked) + '\n\nReply: {"feasible": bool, "reason": str, "files": [up to 5 paths from the list]}. '
              "feasible=false if the issue is vague, a feature request needing design decisions, needs "
              "hardware/credentials/network to verify, or cannot be fixed with a small change.")

        def v1(o: dict) -> None:
            if not isinstance(o.get("feasible"), bool) or not isinstance(o.get("files", []), list):
                raise ValueError("schema: need feasible:bool, files:list")

        s1 = self.llm.ask_json(system, p1, v1)
        self.report.provider = self.llm.used
        if not s1["feasible"]:
            raise Reject(f"AI: not actionable: {str(s1.get('reason', ''))[:160]}")
        picked = [f for f in s1.get("files", []) if isinstance(f, str) and f in tracked][:5]
        if not picked:
            raise Reject("AI selected no valid files")

        # stage 2: propose the smallest correct patch
        chunks, budget = [], 14000
        for f in picked:
            text = (repo_dir / f).read_text(encoding="utf-8", errors="replace")[:6000]
            chunks.append(f"=== {f} ===\n{text}")
            budget -= len(text)
            if budget <= 0:
                break
        test_files = [f for f in files if re.search(r"(^|/)(tests?|__tests__)/", f)][:40]
        p2 = (f"Issue #{number}: {title}\n\n{body}\n\nRelevant files:\n" + "\n\n".join(chunks)
              + "\n\nExisting test files:\n" + "\n".join(test_files)
              + '\n\nReply: {"feasible": bool, "reason": str, "summary": str, "edits": [{"path": str, "old": str, "new": str}], '
              '"new_files": [{"path": str, "content": str}]}. Rules: smallest correct fix for the root cause; "old" must be '
              'copied EXACTLY from a file above and occur exactly once; no cosmetic or unrelated changes; add a regression '
              'test as a new file (new_files) when the project has tests; follow existing conventions.')

        def v2(o: dict) -> None:
            if not isinstance(o.get("feasible"), bool) or not isinstance(o.get("edits", []), list) \
                    or not isinstance(o.get("new_files", []), list):
                raise ValueError("schema: need feasible:bool, edits:list, new_files:list")

        s2 = self.llm.ask_json(system, p2, v2)
        if not s2["feasible"]:
            raise Reject(f"AI: no safe fix: {str(s2.get('reason', ''))[:160]}")

        spec = detect_tests(repo_dir, files)
        py = self.prepare_env(work, repo_dir) if spec and spec["name"] == "pytest" else sys.executable
        if spec:
            base = self.run_tests(repo_dir, spec, py)
            if not base["passed"]:
                raise Reject("baseline tests already fail upstream; cannot attribute results: " + base["detail"][-150:])

        changed = apply_plan(repo_dir, s2, tracked)
        code_changed = any(Path(f).suffix.lower() in CODE_EXTS for f in changed)
        if code_changed and not spec:
            raise Reject("code change but upstream has no runnable test command")
        problems = syntax_check(repo_dir, changed)
        if problems:
            raise Reject("; ".join(problems)[:300])
        if spec:
            res = self.run_tests(repo_dir, spec, py)
            self.report.tests.append({**res, "issue": url})
            if not res["passed"]:
                self.report.test_failures += 1
                raise Reject(f"tests failed after patch: {res['detail'][-200:]}")
        else:
            self.report.tests.append({"cmd": "syntax checks only (docs/config change, no upstream tests)",
                                      "passed": True, "detail": ""})

        run(["git", "add", "--", *changed], cwd=repo_dir)  # only the patched files, never test artifacts
        diff = run(["git", "diff", "--cached"], cwd=repo_dir).stdout
        staged = set(run(["git", "diff", "--cached", "--name-only"], cwd=repo_dir).stdout.split())
        if staged != set(changed):
            raise Reject("unexpected files in diff (build artifacts?)")
        leak = scan_secrets(diff)
        if leak:
            raise Reject(leak)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "patch.diff").write_text(diff)
        self.report.selected_issue = {"url": url, "title": title}
        self.report.files = changed

        if self.dry_run or not self.pat:
            self.report.status = "validated_no_pr"
            self.report.summary = "Patch validated, PR not opened (" + ("dry run" if self.dry_run else "no GH_PAT secret") + ")."
            return
        self.report.pr_url = self.open_pr(owner, repo, info, item, s2.get("summary", ""), repo_dir, changed)
        self.report.status = "pr_created"
        self.report.summary = "Pull request opened."

    def open_pr(self, owner: str, repo: str, info: dict, item: dict, summary: str, repo_dir: Path,
                changed: list[str]) -> str:
        number = item["number"]
        # re-verify right before opening: issue still open, no PR appeared meanwhile
        fresh = self.gh.get(f"/repos/{owner}/{repo}/issues/{number}")
        if fresh.get("state") != "open":
            raise Reject("issue was closed before the PR could be opened")
        self.check_linked_prs(owner, repo, number)
        me = self.gh.get("/user")
        login = me["login"]
        self.gh.post(f"/repos/{owner}/{repo}/forks", {"default_branch_only": True})
        for _ in range(12):  # fork creation is asynchronous
            try:
                self.gh.get(f"/repos/{login}/{repo}")
                break
            except (PermanentError, TransientError):
                sleep(5)
        else:
            raise Reject("fork did not become available in time")
        branch = f"ai-fix/issue-{number}"
        ident = ["-c", f"user.name={login}", "-c", f"user.email={me['id']}+{login}@users.noreply.github.com"]
        r = run(["git", *ident, "checkout", "-b", branch], cwd=repo_dir)
        r = run(["git", *ident, "commit", "-m", f"Fix #{number}: {item['title'][:60]}"], cwd=repo_dir)
        if r.returncode != 0:
            raise Reject(f"commit failed: {redact(tail(r.stderr, 200))}")
        auth = base64.b64encode(f"x-access-token:{self.pat}".encode()).decode()
        r = run(["git", "-c", f"http.extraheader=AUTHORIZATION: basic {auth}", "push",
                 f"https://github.com/{login}/{repo}.git", f"{branch}:{branch}"], cwd=repo_dir, timeout=300)
        if r.returncode != 0:
            raise Reject(f"push failed: {redact(tail(r.stderr, 300))}")
        tests = "; ".join(f"{t['cmd']}: {'passed' if t['passed'] else 'FAILED'}" for t in self.report.tests[-1:])
        body = (f"Fixes #{number}\n\n## What\n{summary or item['title']}\n\n## Files changed\n"
                + "\n".join(f"- `{f}`" for f in changed)
                + f"\n\n## Testing\n{tests}. The upstream test command also passed before the change.\n\n"
                "_Prepared with AI assistance; the diff was reviewed by automated checks and the project's own tests._")
        pr = self.gh.post(f"/repos/{owner}/{repo}/pulls", {
            "title": f"Fix #{number}: {item['title'][:70]}", "head": f"{login}:{branch}",
            "base": info["default_branch"], "body": body, "maintainer_can_modify": True})
        return pr["html_url"]

    # ---- discovery-only daily run
    def run(self) -> Report:
        """Find issues and report them; never invoke an LLM or modify code."""
        rep = self.report
        candidates = self.discover()
        rep.discovered = len(candidates)
        log(f"discovered {len(candidates)} unseen candidates")
        by_repo: dict[str, int] = {}
        for item in candidates[:MAX_CANDIDATES]:
            url = item.get("html_url", "")
            rep.examined += 1
            try:
                repo_url = item.get("repository_url", "")
                owner, repo = repo_url.rstrip("/").rsplit("/", 2)[-2:]
                info = self.gh.get(f"/repos/{owner}/{repo}")
                reason = static_reject(item, info)
                if reason:
                    rep.reject(url, reason)
                    continue
                if item.get("comments", 0):
                    comments = self.gh.get(f"/repos/{owner}/{repo}/issues/{item['number']}/comments", per_page=30)
                    reason = comment_reject(comments)
                    if reason:
                        rep.reject(url, reason)
                        continue
                if by_repo.get(f"{owner}/{repo}", 0) >= 2:
                    continue
                labels = [l.get("name", "") if isinstance(l, dict) else str(l) for l in item.get("labels", [])]
                stars = int(info.get("stargazers_count") or 0)
                language = info.get("language") or "Not specified"
                priority_labels = {"good first issue", "help wanted", "beginner", "documentation", "bug"}
                score = sum(4 for label in labels if label.lower() in priority_labels)
                score += min(stars // 250, 8) + max(0, 5 - int(item.get("comments") or 0))
                rep.opportunities.append({
                    "url": url, "title": item.get("title", "Untitled issue"),
                    "repository": f"{owner}/{repo}", "stars": stars, "language": language,
                    "labels": labels[:8], "updated_at": item.get("updated_at", ""),
                    "body": re.sub(r"\s+", " ", (item.get("body") or "").strip())[:650],
                    "score": score,
                })
                by_repo[f"{owner}/{repo}"] = by_repo.get(f"{owner}/{repo}", 0) + 1
                self.seen[url] = {"ts": now().isoformat(), "reason": "sent as opportunity"}
                if len(rep.opportunities) >= 10:
                    break
            except (PermanentError, TransientError) as exc:
                rep.reject(url, f"GitHub/API error: {redact(exc)}")
            except Exception as exc:
                rep.reject(url, f"unexpected {type(exc).__name__}: {redact(exc)[:120]}")
        rep.opportunities.sort(key=lambda x: (x["score"], x["updated_at"]), reverse=True)
        save_seen(self.seen)
        if rep.opportunities:
            rep.status = "opportunities_found"
            rep.summary = f"Found {len(rep.opportunities)} GitHub issues worth reviewing. No code was changed and no PR was created."
        else:
            rep.status = "no_opportunities"
            rep.summary = f"No fresh suitable issues found after checking {rep.examined} candidates."
        return rep

# --------------------------------------------------------------------------- entry points
def cmd_run() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rep = Report(dry_run=os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes"))
    code = 0
    try:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_PAT")
        if not token:
            raise PermanentError("no GitHub token available (GITHUB_TOKEN)")
        # Discovery-only mode: deliberately no LLM/provider initialization.
        Agent(GH(token), None, rep, None, rep.dry_run).run()
    except Exception as exc:
        rep.status, rep.error, code = "crashed", f"{type(exc).__name__}: {redact(exc)[:400]}", 1
    (OUT_DIR / "report.json").write_text(json.dumps(rep.__dict__, indent=1, default=str))
    log(f"status={rep.status} examined={rep.examined} opportunities={len(rep.opportunities)}")
    return code

ICONS = {"opportunities_found": "🔎", "no_opportunities": "📭", "crashed": "💥"}


def format_report(rep: dict, run_url: str) -> str:
    lines = [
        f"{ICONS.get(rep.get('status'), '❔')} Daily GitHub Opportunity Finder",
        f"Status: {rep.get('status', 'unknown')}",
        rep.get("summary") or "",
        f"🔍 Found: {rep.get('discovered', 0)} | Checked: {rep.get('examined', 0)}",
        "",
    ]
    opportunities = rep.get("opportunities", [])
    for i, item in enumerate(opportunities, 1):
        labels = ", ".join(item.get("labels") or []) or "No labels"
        body = item.get("body") or "No description provided."
        lines.extend([
            f"{i}. {item.get('title', 'Untitled issue')}",
            f"📦 {item.get('repository', 'Unknown repo')} | ⭐ {item.get('stars', 0)} | {item.get('language', 'Unknown')}",
            f"🏷 {labels}", f"📝 {body}", f"🔗 {item.get('url', '')}", "",
        ])
    if not opportunities:
        lines.append("Try again tomorrow; no suitable fresh issues were found today.")
    lines.extend([
        "💡 Open the issue, read CONTRIBUTING.md, check recent comments, then comment that you want to work on it before coding.",
        "🤝 Discovery only: no AI, code edits, project tests, or pull requests.",
        f"Run: {run_url}",
    ])
    if rep.get("error"):
        lines.append(f"Error: {rep['error']}")
    return redact("\n".join(lines))

def cmd_telegram() -> int:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured; cannot report.")
        return 1
    run_url = "{}/{}/actions/runs/{}".format(os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
                                             os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", ""))
    try:
        rep = json.loads((OUT_DIR / "report.json").read_text())
    except (OSError, ValueError):
        rep = {"status": "crashed", "summary": "The agent step produced no report.",
               "error": f"agent step outcome: {os.environ.get('AGENT_OUTCOME', 'unknown')}"}
    text = format_report(rep, run_url)
    for i in range(0, len(text), 4000):
        try:
            request_with_retry("POST", f"https://api.telegram.org/bot{token}/sendMessage", retries=3,
                               json={"chat_id": chat, "text": text[i:i + 4000], "disable_web_page_preview": True})
        except (PermanentError, TransientError) as exc:
            log(f"ERROR: Telegram delivery failed: {redact(exc)}")
            return 1
    log("Telegram report sent.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["run", "telegram"])
    args = ap.parse_args()
    return cmd_run() if args.command == "run" else cmd_telegram()


if __name__ == "__main__":
    sys.exit(main())