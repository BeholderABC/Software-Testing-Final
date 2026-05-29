"""
build_traceability.py  --  Generate the project-wide Traceability Matrix.

Reads three sources of truth and writes a single Markdown matrix that
links every requirement to its coverage items, generated test cases, and
hand-written PyTest functions.

Sources
-------
1. data/mini_ecommerce_requirements.json
   The canonical requirement set (REQ-001 .. REQ-012) with feature names
   and expected behaviour summaries.
2. data/baseline/test_cases.json
   The deterministic rule-pipeline baseline. Provides per-requirement
   coverage items + EP / BVA / DT test cases.
3. tests/test_*.py
   AST-parsed for top-level `def test_*` functions; their docstrings are
   tagged with `REQ-NNN / coverage_type` for the hand-written column.

Output
------
docs/traceability_matrix.md  (overwritten in place)

Run
---
    python3 scripts/build_traceability.py
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = PROJECT_ROOT / "data" / "mini_ecommerce_requirements.json"
BASELINE_PATH = PROJECT_ROOT / "data" / "baseline" / "test_cases.json"
TESTS_DIR = PROJECT_ROOT / "tests" / "integration"
OUTPUT_PATH = PROJECT_ROOT / "docs" / "traceability_matrix.md"

# Hand-written tests we want to include in the matrix.
INTEGRATION_FILES = (
    "test_mini_ecommerce_api.py",
    "test_order_api.py",
    "test_order_status_api.py",
)

# Markers we look for inside test function docstrings, e.g.
#   "REQ-009 / boundary: ..."  →  ("REQ-009", "boundary")
DOCSTRING_RE = re.compile(
    r"\b(REQ-\d{3})\b\s*[/:]\s*(positive|negative|boundary|combination|"
    r"decision-table|invariant|side-effect)?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_requirements() -> Dict[str, Dict]:
    """Return REQ-id -> {feature, expected_behavior[]}."""
    payload = json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    return {r["requirement_id"]: r for r in payload.get("requirements", [])}


def load_baseline_test_cases() -> List[Dict]:
    """Return the flat list of test cases produced by the rule pipeline."""
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return payload.get("test_cases", [])


def scan_handwritten_tests() -> Dict[str, List[Dict]]:
    """Return REQ-id -> [{file, function, coverage_type, docstring_summary}].

    Uses ast so we don't import the test modules (which would touch
    `requests` and trigger backend probes).
    """
    by_requirement: Dict[str, List[Dict]] = defaultdict(list)
    for name in INTEGRATION_FILES:
        path = TESTS_DIR / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            docstring = ast.get_docstring(node) or ""
            match = DOCSTRING_RE.search(docstring)
            if not match:
                continue
            rid = match.group(1).upper()
            ctype = (match.group(2) or "").lower()
            first_line = docstring.strip().splitlines()[0]
            by_requirement[rid].append({
                "file": name,
                "function": node.name,
                "coverage_type": ctype,
                "summary": first_line,
            })
    return by_requirement


# ---------------------------------------------------------------------------
# Matrix rendering
# ---------------------------------------------------------------------------

def _requirement_blurb(req: Dict) -> str:
    """One-line summary of the requirement for the matrix's first column."""
    feature = req.get("feature", "")
    behaviour = (req.get("expected_behavior") or [""])[0]
    return f"{feature} — {behaviour}".strip(" —")


def _group_baseline_by_requirement(cases: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for tc in cases:
        rid = str(tc.get("requirement_id", ""))
        if rid:
            grouped[rid].append(tc)
    return grouped


def render(requirements: Dict[str, Dict],
            baseline_by_req: Dict[str, List[Dict]],
            handwritten_by_req: Dict[str, List[Dict]]) -> str:
    lines: List[str] = []
    lines.append("# Traceability Matrix")
    lines.append("")
    lines.append("## Abstract")
    lines.append("")
    lines.append(
        "This matrix records the bidirectional trace adopted by "
        "AutoTestDesign: every requirement is mapped to its coverage "
        "items, the test cases generated from those items by the rule "
        "pipeline baseline, and the hand-written PyTest functions that "
        "exercise the corresponding behaviour against the target "
        "application. The matrix is produced from three sources of "
        "truth — the requirement set, the persisted baseline, and the "
        "test source — and is regenerated by "
        "[scripts/build_traceability.py](../scripts/build_traceability.py).")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- 1. summary table -------------------------------------------------
    lines.append("## 1. Coverage Summary")
    lines.append("")
    lines.append(
        "Table 1 records the per-requirement counts of generated test "
        "cases and hand-written PyTest functions.")
    lines.append("")
    lines.append("**Table 1.** Per-requirement coverage counts.")
    lines.append("")
    lines.append(
        "| Requirement | Feature | Generated cases | Hand-written tests |")
    lines.append("|---|---|---:|---:|")
    total_generated = 0
    total_handwritten = 0
    for rid in sorted(requirements.keys()):
        req = requirements[rid]
        feature = req.get("feature", "")
        gen = len(baseline_by_req.get(rid, []))
        hand = len(handwritten_by_req.get(rid, []))
        total_generated += gen
        total_handwritten += hand
        lines.append(f"| `{rid}` | {feature} | {gen} | {hand} |")
    lines.append(
        f"| **Total** | | **{total_generated}** | **{total_handwritten}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- 2. per-requirement detail ---------------------------------------
    lines.append("## 2. Per-Requirement Detail")
    lines.append("")
    lines.append(
        "Each requirement is recorded below together with its expected "
        "behaviour, the test cases generated by the rule pipeline, and "
        "the hand-written PyTest functions that exercise it.")
    lines.append("")

    for rid in sorted(requirements.keys()):
        req = requirements[rid]
        lines.append(f"### {rid} — {req.get('feature', '')}")
        lines.append("")
        for behaviour in req.get("expected_behavior", []):
            lines.append(f"- {behaviour}")
        lines.append("")

        gens = baseline_by_req.get(rid, [])
        hands = handwritten_by_req.get(rid, [])

        if gens:
            lines.append(
                "Generated test cases, taken from the rule pipeline "
                "baseline persisted at "
                "[data/baseline/test_cases.json](../data/baseline/test_cases.json):")
            lines.append("")
            lines.append(
                "| Test case ID | Technique | Coverage type | Strategy |")
            lines.append("|---|---|---|---|")
            for tc in gens:
                strategy = (tc.get("traceability", {}) or {}).get(
                    "coverage_strategy", "")
                lines.append(
                    f"| `{tc.get('test_case_id', '')}` | "
                    f"{tc.get('test_design_technique', '')} | "
                    f"{tc.get('coverage_type', '')} | "
                    f"{strategy} |")
            lines.append("")

        if hands:
            lines.append(
                "Hand-written PyTest functions tagged for this "
                "requirement:")
            lines.append("")
            lines.append(
                "| PyTest function | File | Coverage type | Summary |")
            lines.append("|---|---|---|---|")
            for hw in hands:
                rel_file = f"tests/integration/{hw['file']}"
                lines.append(
                    f"| `{hw['function']}` | "
                    f"[`{rel_file}`](../{rel_file}) | "
                    f"{hw['coverage_type'] or '-'} | "
                    f"{hw['summary']} |")
            lines.append("")

        if not gens and not hands:
            lines.append("_No traced artefacts have been recorded._")
            lines.append("")

    lines.append("---")
    lines.append("")

    # --- 3. conventions --------------------------------------------------
    lines.append("## 3. Conventions")
    lines.append("")
    lines.append(
        "Coverage-type values follow "
        "[STYLE_GUIDE.md](STYLE_GUIDE.md) §1.4. The mapping from "
        "coverage type to test design technique is recorded in "
        "[test_design.md](test_design.md) §3. Hand-written tests "
        "declare their originating requirement and coverage type in "
        "the docstring, for example "
        "`\"\"\"REQ-009 / boundary: …\"\"\"`; the generator extracts "
        "this tag by AST inspection rather than module import, so the "
        "regeneration step is free of backend probes.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> Tuple[Path, int, int]:
    requirements = load_requirements()
    baseline = load_baseline_test_cases()
    handwritten = scan_handwritten_tests()

    baseline_by_req = _group_baseline_by_requirement(baseline)
    content = render(requirements, baseline_by_req, handwritten)
    OUTPUT_PATH.write_text(content, encoding="utf-8")

    total_gen = sum(len(v) for v in baseline_by_req.values())
    total_hand = sum(len(v) for v in handwritten.values())
    return OUTPUT_PATH, total_gen, total_hand


if __name__ == "__main__":
    path, gen, hand = main()
    print(f"Wrote {path.relative_to(PROJECT_ROOT)}")
    print(f"  Generated test cases traced: {gen}")
    print(f"  Hand-written tests traced:   {hand}")
