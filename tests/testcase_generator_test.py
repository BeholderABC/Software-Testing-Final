"""
Tests for core/testcase_generator.py

Run from the project root:
    python tests/testcase_generator_test.py
(or just Run this file in PyCharm)

The tests:
  - load data/sample_coverage.json and data/sample_risk_analysis.json
  - generate test cases
  - assert all three black-box techniques are present
  - check id format, traceability and the risk -> priority mapping
  - verify the manual-review fallback via a synthetic 'fallback' item
  - print formatted JSON for screenshots / the report
"""

import json
import os
import sys
import unittest

# make `core` importable both from the command line and from PyCharm
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.testcase_generator import (  # noqa: E402
    generate_test_cases,
    infer_test_data,
    infer_expected_result,
    build_summary,
    TECH_EP,
    TECH_BVA,
    TECH_DT,
    TECH_MANUAL,
)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# the documented risk_level -> priority mapping used across the engine
RISK_TO_PRIORITY = {"High": "High", "Medium": "Medium", "Low": "Low"}


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


class TestTestCaseGenerator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.coverage = _load("sample_coverage.json")
        cls.risk = _load("sample_risk_analysis.json")
        cls.result = generate_test_cases(cls.coverage, cls.risk)
        cls.cases = cls.result["test_cases"]

    def test_loads_and_generates(self):
        self.assertGreater(len(self.cases), 0, "no test cases generated")
        self.assertIn("summary", self.result)
        self.assertEqual(self.result["summary"]["total"], len(self.cases))

    def test_three_techniques_present(self):
        techniques = {c["test_design_technique"] for c in self.cases}
        for tech in (TECH_EP, TECH_BVA, TECH_DT):
            self.assertIn(tech, techniques,
                          "expected technique missing: " + tech)

    def test_id_format_and_uniqueness(self):
        ids = [c["test_case_id"] for c in self.cases]
        self.assertEqual(len(ids), len(set(ids)), "duplicate test_case_id")
        for c in self.cases:
            self.assertTrue(
                c["test_case_id"].startswith("TC-" + c["requirement_id"] + "-"),
                "bad id format: " + c["test_case_id"])

    def test_traceability_present(self):
        for c in self.cases:
            tr = c["traceability"]
            self.assertEqual(tr["source_requirement"], c["requirement_id"])
            self.assertIn("coverage_strategy", tr)

    def test_risk_to_priority_mapping(self):
        # data-agnostic: every case's priority must follow risk_level -> priority
        for c in self.cases:
            self.assertEqual(
                c["priority"], RISK_TO_PRIORITY.get(c["risk_level"], "Medium"),
                "priority does not match risk_level for " + c["test_case_id"])

    def test_fallback_is_flagged_for_manual_review(self):
        # the sample data may not contain a 'fallback' item, so we feed one in
        synthetic = {
            "coverage": [{
                "requirement_id": "RX",
                "feature": "Synthetic feature",
                "coverage_items": [
                    {"description": "unsupported locale", "type": "fallback"}
                ]
            }]
        }
        res = generate_test_cases(synthetic, None)
        case = res["test_cases"][0]
        self.assertEqual(case["test_design_technique"], TECH_MANUAL)
        self.assertTrue(case["need_manual_review"])

    def test_infer_test_data_rules(self):
        self.assertEqual(infer_test_data("username already exists", "negative"),
                         {"username": "existing_user"})
        self.assertEqual(infer_test_data("username is new unique value", "positive"),
                         {"username": "new_user_001"})
        self.assertEqual(infer_test_data("username is empty", "boundary"),
                         {"username": ""})
        self.assertEqual(infer_test_data("password length = 7", "boundary"),
                         {"password": "A1bcdef"})
        self.assertEqual(len(infer_test_data("password length = 20", "boundary")["password"]),
                         20)
        # works even with A's richer descriptions like "missing uppercase (has [...])"
        self.assertEqual(infer_test_data("missing uppercase (has ['lowercase'])", "negative"),
                         {"password": "abc12345"})

    def test_infer_expected_result_boundary(self):
        # 7 is below the 8..20 range -> reject; 8 is in range -> accept
        self.assertIn("reject", infer_expected_result("password length = 7", "boundary").lower())
        self.assertIn("accept", infer_expected_result("password length = 8", "boundary").lower())

    def test_empty_input_is_tolerated(self):
        empty = generate_test_cases({}, None)
        self.assertEqual(empty["test_cases"], [])
        self.assertEqual(empty["summary"]["total"], 0)

    def test_missing_risk_defaults_to_medium(self):
        res = generate_test_cases(self.coverage, None)
        self.assertTrue(all(c["risk_level"] == "Medium" for c in res["test_cases"]))
        self.assertTrue(all(c["priority"] == "Medium" for c in res["test_cases"]))

    def test_build_summary_counts(self):
        summary = build_summary(self.cases)
        self.assertEqual(sum(summary["by_technique"].values()), len(self.cases))
        self.assertEqual(sum(summary["by_priority"].values()), len(self.cases))


def _print_demo():
    coverage = _load("sample_coverage.json")
    risk = _load("sample_risk_analysis.json")
    result = generate_test_cases(coverage, risk)
    print("=" * 70)
    print("GENERATED TEST CASES (sample_coverage.json + sample_risk_analysis.json)")
    print("=" * 70)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _print_demo()
    print("\n" + "=" * 70)
    print("RUNNING UNIT TESTS")
    print("=" * 70)
    unittest.main(verbosity=2)
