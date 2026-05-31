"""
test_runner.py  --  Drive the data-driven PyTest harness from inside Streamlit.

The Streamlit UI uses this module to:
  1. Persist the current set of generated test cases to a temporary JSON.
  2. Spawn pytest in a subprocess against
     `tests/integration/test_data_driven_orders.py`, telling it where the JSON lives
     and which backend URL to hit via environment variables.
  3. Parse pytest's text report into structured per-case results so the UI
     can render a colourful summary table instead of raw text.

Pytest is invoked as a subprocess (not via `pytest.main(...)`) so that:
  - The Streamlit process keeps a clean import cache.
  - Test collection / Django HTTP calls do not block the main thread's
    asyncio loop.
  - The cwd / env vars given to the runner do not leak into Streamlit.

The parser intentionally relies only on pytest's default `--tb=line -q`
output. No third-party pytest plugin is required.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HARNESS = "tests/integration/test_data_driven_orders.py"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000/api"


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """One test case result, ready for the Streamlit table."""

    nodeid: str
    test_case_id: str
    requirement_id: str
    coverage_type: str
    outcome: str            # "passed" | "failed" | "skipped" | "error"
    duration_ms: float = 0.0
    message: str = ""

    def as_row(self) -> Dict[str, Any]:
        return {
            "test_case_id": self.test_case_id,
            "requirement_id": self.requirement_id,
            "coverage_type": self.coverage_type,
            "outcome": self.outcome.upper(),
            "duration_ms": round(self.duration_ms, 1),
            "message": self.message,
        }


@dataclass
class RunSummary:
    """Aggregate counts + raw stdout, mirroring pytest's tail line."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    backend_url: str = ""
    test_cases_path: str = ""
    raw_output: str = ""
    return_code: int = 0
    results: List[TestResult] = field(default_factory=list)

    def is_clean(self) -> bool:
        return self.failed == 0 and self.errors == 0


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def write_test_cases(test_cases: List[Dict[str, Any]],
                     output_dir: Optional[Path] = None) -> Path:
    """Write the live test-case list to a JSON file the harness can read.

    The file lives in outputs/ so the user can grab it for the report later.
    """
    out = output_dir or (PROJECT_ROOT / "outputs")
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out / f"_streamlit_run_{ts}.json"
    payload = {"test_cases": test_cases}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Pytest invocation
# ---------------------------------------------------------------------------

_PROXY_ENV_VARS = (
    "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
    "HTTPS_PROXY", "https_proxy",
)


def _build_env(backend_url: str, test_cases_path: Path,
               full_http_exec: bool = False) -> Dict[str, str]:
    env = os.environ.copy()
    env["BACKEND_BASE_URL"] = backend_url
    env["GENERATED_TEST_CASES"] = str(test_cases_path)
    if full_http_exec:
        env["FULL_HTTP_EXEC"] = "1"
    else:
        env.pop("FULL_HTTP_EXEC", None)

    # A local backend must never be reached through a proxy. A SOCKS/HTTP
    # proxy inherited from the shell (common on macOS) would hijack the
    # 127.0.0.1 requests and make every test fail to connect. For a local
    # target we strip the proxy variables outright (NO_PROXY alone is
    # unreliable when ALL_PROXY points at a SOCKS endpoint).
    if any(h in backend_url for h in ("127.0.0.1", "localhost", "0.0.0.0")):
        for var in _PROXY_ENV_VARS:
            env.pop(var, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


def _pytest_argv(target: str) -> List[str]:
    return [
        sys.executable, "-m", "pytest", target,
        "-v",
        "--tb=line",
        "-rN",   # don't repeat the short summary; we read the per-line output
    ]


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------

_NODE_RE = re.compile(
    r"^(?P<nodeid>\S+?\.py::\S+?)(?:\s+(?P<outcome>PASSED|FAILED|SKIPPED|ERROR))"
    r"(?:\s+\[\s*\d+%\])?\s*$"
)
_SUMMARY_RE = re.compile(
    r"=+\s*(?:(?P<failed>\d+)\s+failed[,\s]+)?"
    r"(?:(?P<passed>\d+)\s+passed[,\s]+)?"
    r"(?:(?P<skipped>\d+)\s+skipped[,\s]+)?"
    r"(?:(?P<errors>\d+)\s+errors?[,\s]+)?"
    r"in\s+(?P<duration>[\d.]+)s",
    re.IGNORECASE,
)
_FAIL_LINE_RE = re.compile(r"^(?P<nodeid>\S+?\.py::\S+?):\s+(?P<msg>.+)$")


def _split_nodeid(nodeid: str) -> Dict[str, str]:
    """Extract the test_case_id / requirement_id / coverage_type from the
    parametrised nodeid produced by test_data_driven_orders.py.

    Example nodeid:
        tests/integration/test_data_driven_orders.py::test_generated_case_drives_backend[TC-REQ-009-002::boundary]
    """
    bracket_match = re.search(r"\[(?P<param>[^\]]+)\]", nodeid)
    if not bracket_match:
        return {"test_case_id": nodeid.split("::")[-1],
                "requirement_id": "",
                "coverage_type": ""}
    param = bracket_match.group("param")
    if "::" in param:
        tc_id, ctype = param.split("::", 1)
    else:
        tc_id, ctype = param, ""
    rid_match = re.match(r"TC-(REQ-\d+)-", tc_id)
    rid = rid_match.group(1) if rid_match else ""
    return {"test_case_id": tc_id, "requirement_id": rid,
            "coverage_type": ctype}


def parse_pytest_output(stdout: str) -> List[TestResult]:
    """Translate pytest -v --tb=line output into TestResult rows."""
    results: List[TestResult] = []
    fail_messages: Dict[str, str] = {}

    for raw_line in stdout.splitlines():
        line = raw_line.rstrip()
        m = _NODE_RE.match(line)
        if m:
            meta = _split_nodeid(m.group("nodeid"))
            results.append(TestResult(
                nodeid=m.group("nodeid"),
                test_case_id=meta["test_case_id"],
                requirement_id=meta["requirement_id"],
                coverage_type=meta["coverage_type"],
                outcome=m.group("outcome").lower(),
            ))
            continue
        fm = _FAIL_LINE_RE.match(line)
        if fm:
            fail_messages[fm.group("nodeid")] = fm.group("msg").strip()

    # Attach failure / skip messages where available
    for r in results:
        if r.outcome in ("failed", "error") and r.nodeid in fail_messages:
            r.message = fail_messages[r.nodeid]
    return results


def parse_summary(stdout: str) -> Dict[str, Any]:
    """Pull totals out of pytest's tail line (`=== 35 passed, 1 failed in 2.4s ===`)."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0,
              "duration": 0.0}
    for line in reversed(stdout.splitlines()):
        m = _SUMMARY_RE.search(line)
        if m:
            counts["passed"] = int(m.group("passed") or 0)
            counts["failed"] = int(m.group("failed") or 0)
            counts["skipped"] = int(m.group("skipped") or 0)
            counts["errors"] = int(m.group("errors") or 0)
            counts["duration"] = float(m.group("duration") or 0.0)
            break
    return counts


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_data_driven_tests(test_cases: List[Dict[str, Any]],
                          backend_url: str = DEFAULT_BACKEND_URL,
                          harness: str = DEFAULT_HARNESS,
                          timeout: float = 120.0,
                          project_root: Optional[Path] = None,
                          full_http_exec: bool = False) -> RunSummary:
    """Run the data-driven harness against `test_cases` and parse the result.

    Returns a RunSummary populated with per-case rows and aggregate counts.

    When ``full_http_exec`` is True the harness is told (via the
    ``FULL_HTTP_EXEC=1`` environment variable) to *not* collapse cases
    that share the same ``(requirement_id, coverage_type,
    event_sequence)`` key. Every case is then exercised as a separate
    HTTP request. This is the diagnostic mode used to demonstrate that
    the deduplicated and full executions agree.
    """
    root = project_root or PROJECT_ROOT
    cases_path = write_test_cases(test_cases, root / "outputs")
    env = _build_env(backend_url, cases_path, full_http_exec=full_http_exec)

    try:
        completed = subprocess.run(
            _pytest_argv(harness),
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = completed.stdout or ""
        return_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout.decode() if isinstance(exc.stdout, (bytes, bytearray))
                  else (exc.stdout or "")) + "\n[runner] timeout"
        return_code = -1

    results = parse_pytest_output(stdout)
    summary = parse_summary(stdout)

    # Promote per-case durations from average when pytest didn't print them.
    if summary["duration"] and results:
        per_case = (summary["duration"] * 1000.0) / max(len(results), 1)
        for r in results:
            r.duration_ms = per_case

    return RunSummary(
        total=len(results),
        passed=summary["passed"],
        failed=summary["failed"],
        skipped=summary["skipped"],
        errors=summary["errors"],
        duration_seconds=summary["duration"],
        backend_url=backend_url,
        test_cases_path=str(cases_path.relative_to(root)),
        raw_output=stdout,
        return_code=return_code,
        results=results,
    )


# ---------------------------------------------------------------------------
# Backend status helper (probe only; never spawns the server)
# ---------------------------------------------------------------------------

def probe_backend(base_url: str, timeout: float = 1.0) -> Dict[str, Any]:
    """Return {alive: bool, status_code: int|None, error: str|None}."""
    try:
        import requests
    except ImportError:
        return {"alive": False, "status_code": None,
                "error": "requests not installed"}
    try:
        r = requests.get(f"{base_url.rstrip('/')}/products/", timeout=timeout)
        return {"alive": r.status_code < 500,
                "status_code": r.status_code, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"alive": False, "status_code": None, "error": str(exc)}


# Manual smoke test (run with `python -m core.test_runner`)
if __name__ == "__main__":
    from core import pipeline_fallback, testcase_generator

    SAMPLE = """REQ-007: The system shall reject an order if the items array is empty.
REQ-009: The system shall reject an order if requested quantity exceeds available stock."""

    req_df = pipeline_fallback.parse_requirements(SAMPLE)
    risk_df = pipeline_fallback.analyze_risk(req_df)
    cov_df = pipeline_fallback.generate_coverage_items(req_df, risk_df)
    cov_json = pipeline_fallback.coverage_df_to_engine_json(cov_df, req_df)
    risk_json = pipeline_fallback.risk_df_to_engine_json(risk_df)
    tc = testcase_generator.generate_test_cases(cov_json, risk_json)

    sm = run_data_driven_tests(tc["test_cases"])
    print(f"Total: {sm.total} | Passed: {sm.passed} | Failed: {sm.failed} | Skipped: {sm.skipped}")
    for r in sm.results[:5]:
        print(" ", r.test_case_id, r.coverage_type, r.outcome,
              r.message[:60])
