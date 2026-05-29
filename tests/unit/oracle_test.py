"""Unit tests for core/oracle.py (FR 5.0)."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import oracle  # noqa: E402


SAMPLE_REQ = {
    "requirement_id": "REQ-009",
    "feature": "Reject order whose quantity exceeds stock",
    "expected_behavior": [
        "system rejects the order and returns 400 Bad Request",
    ],
}


class TestOracle(unittest.TestCase):

    # --- positive / negative defaults ------------------------------------

    def test_positive_case_expects_2xx(self):
        o = oracle.derive_oracle(
            coverage_item="happy path", coverage_type="positive")
        self.assertEqual((o["http_status_min"], o["http_status_max"]),
                         (200, 201))

    def test_negative_case_expects_400(self):
        o = oracle.derive_oracle(
            coverage_item="reject", coverage_type="negative")
        self.assertEqual((o["http_status_min"], o["http_status_max"]),
                         (400, 400))

    # --- boundary heuristics ---------------------------------------------

    def test_boundary_in_range_is_accepted(self):
        o = oracle.derive_oracle(
            coverage_item="quantity equal to stock",
            coverage_type="boundary")
        self.assertEqual((o["http_status_min"], o["http_status_max"]),
                         (200, 201))

    def test_boundary_zero_is_rejected(self):
        o = oracle.derive_oracle(
            coverage_item="quantity = 0",
            coverage_type="boundary")
        self.assertEqual((o["http_status_min"], o["http_status_max"]),
                         (400, 400))

    def test_boundary_exceeds_is_rejected(self):
        o = oracle.derive_oracle(
            coverage_item="quantity > stock",
            coverage_type="boundary")
        self.assertEqual((o["http_status_min"], o["http_status_max"]),
                         (400, 400))

    # --- keyword extraction ---------------------------------------------

    def test_keywords_lifted_for_negative_case(self):
        o = oracle.derive_oracle(
            coverage_item="reject empty items",
            coverage_type="negative",
            requirement=SAMPLE_REQ)
        # at least one of the lifted words should be domain-flavoured
        self.assertTrue(o["must_contain"])
        self.assertTrue(all(isinstance(k, str) for k in o["must_contain"]))

    def test_keywords_not_lifted_for_positive_case(self):
        o = oracle.derive_oracle(
            coverage_item="valid happy path",
            coverage_type="positive",
            requirement=SAMPLE_REQ)
        self.assertEqual(o["must_contain"], [])

    # --- attach_oracles --------------------------------------------------

    def test_attach_oracles_populates_every_case(self):
        cases = [
            {"test_case_id": "TC-1", "requirement_id": "REQ-009",
             "coverage_item": "quantity > stock",
             "coverage_type": "boundary"},
            {"test_case_id": "TC-2", "requirement_id": "REQ-009",
             "coverage_item": "valid happy path",
             "coverage_type": "positive"},
        ]
        oracle.attach_oracles(cases, [SAMPLE_REQ])
        for tc in cases:
            self.assertIn("oracle", tc)
            self.assertIn("http_status_min", tc["oracle"])

    def test_attach_oracles_is_idempotent(self):
        existing = {"http_status_min": 418, "http_status_max": 418,
                    "must_contain": ["teapot"], "must_not_contain": [],
                    "side_effect": {}}
        cases = [{
            "test_case_id": "TC-X", "requirement_id": "REQ-009",
            "coverage_item": "anything", "coverage_type": "positive",
            "oracle": existing,
        }]
        oracle.attach_oracles(cases, [SAMPLE_REQ])
        self.assertEqual(cases[0]["oracle"], existing)


if __name__ == "__main__":
    unittest.main()
