"""
Tests for core/optimizer.py

Run from the project root:
    python tests/optimizer_test.py
(or just Run this file in PyCharm)

The tests:
  - generate a suite from the sample data
  - assert prioritisation orders higher-risk cases before lower-risk ones
  - assert risk-based minimisation keeps >= 1 case per requirement
  - verify (on a synthetic suite) that High risk keeps more than Low risk
  - print formatted JSON for screenshots / the report
"""

import json
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.testcase_generator import generate_test_cases  # noqa: E402
from core.optimizer import (  # noqa: E402
    prioritize_test_cases,
    minimize_test_suite,
    optimize_test_suite,
)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
_RISK_RANK = {"High": 3, "Medium": 2, "Low": 1}


def _load(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


class TestOptimizer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.coverage = _load("sample_coverage.json")
        cls.risk = _load("sample_risk_analysis.json")
        cls.suite = generate_test_cases(cls.coverage, cls.risk)
        cls.cases = cls.suite["test_cases"]

    def test_prioritize_orders_by_risk(self):
        ordered = prioritize_test_cases(self.cases)
        ranks = [_RISK_RANK.get(c["risk_level"], 0) for c in ordered]
        self.assertEqual(ranks, sorted(ranks, reverse=True),
                         "cases are not ordered by descending risk")

    def test_prioritize_does_not_lose_cases(self):
        ordered = prioritize_test_cases(self.cases)
        self.assertEqual(len(ordered), len(self.cases))

    def test_minimize_keeps_one_per_requirement(self):
        minimized = minimize_test_suite(self.cases, mode="risk_based")
        req_ids_in = {c["requirement_id"] for c in self.cases}
        req_ids_out = {c["requirement_id"] for c in minimized}
        self.assertEqual(req_ids_in, req_ids_out,
                         "minimisation dropped an entire requirement")

    def test_minimize_reduces_or_equal(self):
        minimized = minimize_test_suite(self.cases, mode="risk_based")
        self.assertLessEqual(len(minimized), len(self.cases))

    def test_high_risk_keeps_more_than_low(self):
        # synthetic suite so the invariant is checked regardless of A's data:
        # a High-risk requirement with many items vs a Low-risk requirement.
        synthetic_cov = {
            "coverage": [
                {
                    "requirement_id": "HI",
                    "feature": "High risk feature",
                    "coverage_items": [
                        {"description": "a is empty", "type": "boundary"},
                        {"description": "a invalid", "type": "negative"},
                        {"description": "b invalid", "type": "negative"},
                        {"description": "a valid", "type": "positive"},
                    ],
                },
                {
                    "requirement_id": "LO",
                    "feature": "Low risk feature",
                    "coverage_items": [
                        {"description": "x is empty", "type": "boundary"},
                        {"description": "x invalid", "type": "negative"},
                        {"description": "x valid", "type": "positive"},
                    ],
                },
            ]
        }
        synthetic_risk = {"risk_assessment": [
            {"requirement_id": "HI", "risk_level": "High", "risk_score": 9},
            {"requirement_id": "LO", "risk_level": "Low", "risk_score": 2},
        ]}
        suite = generate_test_cases(synthetic_cov, synthetic_risk)
        minimized = minimize_test_suite(suite, mode="risk_based")
        hi = [c for c in minimized if c["requirement_id"] == "HI"]
        lo = [c for c in minimized if c["requirement_id"] == "LO"]
        self.assertGreater(len(hi), len(lo),
                           "high-risk requirement should keep more cases than low-risk")

    def test_optimize_entry_point_summary(self):
        result = optimize_test_suite(self.suite, self.risk, minimize=True)
        self.assertIn("optimized_test_cases", result)
        summ = result["optimization_summary"]
        self.assertEqual(summ["original_count"], len(self.cases))
        self.assertEqual(summ["optimized_count"], len(result["optimized_test_cases"]))
        self.assertEqual(summ["removed_count"],
                         summ["original_count"] - summ["optimized_count"])
        self.assertEqual(summ["strategy"], "risk_based_minimization")

    def test_optimize_prioritize_only_keeps_all(self):
        result = optimize_test_suite(self.suite, self.risk, minimize=False)
        self.assertEqual(result["optimization_summary"]["removed_count"], 0)
        self.assertEqual(result["optimization_summary"]["strategy"],
                         "risk_based_prioritization")

    def test_tolerates_empty_input(self):
        result = optimize_test_suite({"test_cases": []}, None, minimize=True)
        self.assertEqual(result["optimized_test_cases"], [])
        self.assertEqual(result["optimization_summary"]["original_count"], 0)


def _print_demo():
    coverage = _load("sample_coverage.json")
    risk = _load("sample_risk_analysis.json")
    suite = generate_test_cases(coverage, risk)

    prioritized = optimize_test_suite(suite, risk, minimize=False)
    minimized = optimize_test_suite(suite, risk, minimize=True)

    print("=" * 70)
    print("PRIORITISED SUITE SUMMARY (no minimisation)")
    print("=" * 70)
    print(json.dumps(prioritized["optimization_summary"], indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("MINIMISED SUITE (risk_based)")
    print("=" * 70)
    print(json.dumps(minimized, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _print_demo()
    print("\n" + "=" * 70)
    print("RUNNING UNIT TESTS")
    print("=" * 70)
    unittest.main(verbosity=2)
