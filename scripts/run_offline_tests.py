"""
run_offline_tests.py  --  Run the offline unit suite and persist the result.

The offline suite is the set of tool-internal unit tests that need neither
the target backend nor live LLM access:

    pytest tests/unit/
        --ignore=tests/unit/parser_test.py    # LLM smoke (needs API)
        --ignore=tests/unit/risk_test.py       # LLM smoke (needs API)

This script runs exactly that suite, captures pytest's machine-readable
JUnit XML, and writes three timestamped artefacts into ``outputs/`` so the
offline test result can be cited in the report alongside the export and
benchmark artefacts:

    outputs/offline_tests_<ts>.xml   -- raw JUnit XML from pytest
    outputs/offline_tests_<ts>.json  -- parsed per-case + summary results
    outputs/offline_tests_<ts>.md    -- a human-readable summary table

Run
---
    .venv/bin/python scripts/run_offline_tests.py
    .venv/bin/python scripts/run_offline_tests.py --output-dir some/dir
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = PROJECT_ROOT / "outputs/offline"

# The offline suite definition — kept in one place so it matches the README.
UNIT_DIR = "tests/unit/"
IGNORED = (
    "tests/unit/parser_test.py",
    "tests/unit/risk_test.py",
)


# ---------------------------------------------------------------------------
# Run pytest
# ---------------------------------------------------------------------------

def run_pytest(junit_path: Path) -> int:
    """Run the offline unit suite, emitting JUnit XML. Return the exit code."""
    cmd = [
        sys.executable, "-m", "pytest", UNIT_DIR, "-q",
        f"--junit-xml={junit_path}",
    ]
    for ignored in IGNORED:
        cmd.append(f"--ignore={ignored}")
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return proc.returncode


# ---------------------------------------------------------------------------
# Parse JUnit XML
# ---------------------------------------------------------------------------

def parse_junit(junit_path: Path) -> Dict[str, Any]:
    """Parse pytest's JUnit XML into a structured result dictionary."""
    tree = ET.parse(junit_path)
    root = tree.getroot()
    # The root may be <testsuites> wrapping one <testsuite>, or a bare
    # <testsuite>; handle both.
    suite = root.find("testsuite") if root.tag == "testsuites" else root

    cases: List[Dict[str, Any]] = []
    for tc in suite.findall("testcase"):
        outcome = "passed"
        message = ""
        if tc.find("failure") is not None:
            outcome = "failed"
            message = (tc.find("failure").get("message") or "").strip()
        elif tc.find("error") is not None:
            outcome = "error"
            message = (tc.find("error").get("message") or "").strip()
        elif tc.find("skipped") is not None:
            outcome = "skipped"
            message = (tc.find("skipped").get("message") or "").strip()
        cases.append({
            "classname": tc.get("classname", ""),
            "name": tc.get("name", ""),
            "time_s": float(tc.get("time", "0") or 0),
            "outcome": outcome,
            "message": message,
        })

    summary = {
        "total": int(suite.get("tests", "0") or 0),
        "failures": int(suite.get("failures", "0") or 0),
        "errors": int(suite.get("errors", "0") or 0),
        "skipped": int(suite.get("skipped", "0") or 0),
        "time_s": float(suite.get("time", "0") or 0),
    }
    summary["passed"] = (summary["total"] - summary["failures"]
                         - summary["errors"] - summary["skipped"])
    return {"summary": summary, "cases": cases}


# ---------------------------------------------------------------------------
# Render the Markdown report
# ---------------------------------------------------------------------------

def render_markdown(result: Dict[str, Any], generated_at: str) -> str:
    s = result["summary"]
    verdict = "PASS" if s["failures"] == 0 and s["errors"] == 0 else "FAIL"
    lines: List[str] = []
    lines.append("# Offline Test Result")
    lines.append("")
    lines.append("## Abstract")
    lines.append("")
    lines.append(
        "This report records the outcome of the offline unit suite — the "
        "tool-internal tests that need neither the target backend nor live "
        "language-model access. It is produced by "
        "[scripts/run_offline_tests.py](../scripts/run_offline_tests.py) "
        "and persisted under [outputs/](../outputs/) so the offline result "
        "can be cited alongside the export and benchmark artefacts.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Generated at: {generated_at}")
    lines.append(f"- Suite: `pytest {UNIT_DIR}` excluding "
                 + ", ".join(f"`{i}`" for i in IGNORED))
    lines.append(f"- Verdict: **{verdict}**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. Summary")
    lines.append("")
    lines.append("**Table 1.** Aggregate outcome of the offline suite.")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---:|")
    lines.append(f"| Total | {s['total']} |")
    lines.append(f"| Passed | {s['passed']} |")
    lines.append(f"| Failed | {s['failures']} |")
    lines.append(f"| Errors | {s['errors']} |")
    lines.append(f"| Skipped | {s['skipped']} |")
    lines.append(f"| Duration (s) | {s['time_s']:.2f} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Per-Case Results")
    lines.append("")
    lines.append("**Table 2.** Outcome of each offline test case.")
    lines.append("")
    lines.append("| Module | Test | Outcome | Time (ms) |")
    lines.append("|---|---|---|---:|")
    for c in result["cases"]:
        module = c["classname"].split(".")[-1] if c["classname"] else ""
        lines.append(
            f"| {module} | {c['name']} | {c['outcome'].upper()} | "
            f"{c['time_s'] * 1000:.1f} |")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", default=str(OUTPUTS_DIR))
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    junit_path = out_dir / f"offline_tests_{ts}.xml"
    json_path = out_dir / f"offline_tests_{ts}.json"
    md_path = out_dir / f"offline_tests_{ts}.md"

    print(f"Running offline suite: pytest {UNIT_DIR} (excluding LLM smoke)…")
    code = run_pytest(junit_path)

    if not junit_path.exists():
        print("pytest did not produce a JUnit XML; aborting.", file=sys.stderr)
        return code or 1

    result = parse_junit(junit_path)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    result["generated_at"] = generated_at
    result["return_code"] = code

    json_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(
        render_markdown(result, generated_at), encoding="utf-8")

    s = result["summary"]
    print(f"  {s['passed']} passed, {s['failures']} failed, "
          f"{s['errors']} errors, {s['skipped']} skipped "
          f"in {s['time_s']:.2f}s")
    print(f"Wrote:")
    for p in (junit_path, json_path, md_path):
        print(f"  {p.relative_to(PROJECT_ROOT)}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
