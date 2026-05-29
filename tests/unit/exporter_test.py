"""Unit tests for core/exporter.py.

The exporter is the bridge between the rule / LLM pipeline and downstream test
management tools, so these tests focus on:
  - Tolerant input handling (DataFrame, list-of-dicts, generator wrapper dict)
  - Correct file creation with stable filenames
  - Survival of nested fields through the CSV round-trip
  - Excel workbook contains all four sheets
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core import exporter  # noqa: E402


REQUIREMENTS = [
    {"requirement_id": "REQ-001", "raw_requirement": "demo requirement",
     "target_module": "Order Processing"},
]

RISK = [
    {"requirement_id": "REQ-001", "risk_level": "Medium", "risk_score": 5,
     "priority": "Medium"},
]

COVERAGE = [
    {"coverage_item_id": "CI-001", "requirement_id": "REQ-001",
     "coverage_strategy": "Equivalence Partitioning", "priority": "Medium"},
]

TEST_CASES_WRAPPER = {
    "test_cases": [
        {
            "test_case_id": "TC-REQ-001-001",
            "requirement_id": "REQ-001",
            "test_design_technique": "Equivalence Partitioning",
            "test_data": {"product_id": 1, "quantity": 1},
            "steps": ["POST /api/orders/create/"],
            "traceability": {"source_requirement": "REQ-001",
                             "covered_item": "valid order",
                             "coverage_strategy": "positive path coverage"},
        }
    ],
    "summary": {"total": 1, "by_technique": {"Equivalence Partitioning": 1}},
}


class TestExporter(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="exporter_test_")
        self.ts = "20990101_000000"

    def tearDown(self):
        # Best-effort cleanup; failure should not mask test failure.
        for root, _, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            try:
                os.rmdir(root)
            except OSError:
                pass

    # --- normalisation helpers -------------------------------------------

    def test_to_dataframe_accepts_none(self):
        df = exporter._to_dataframe(None)
        self.assertTrue(df.empty)

    def test_to_dataframe_accepts_dataframe(self):
        src = pd.DataFrame(REQUIREMENTS)
        df = exporter._to_dataframe(src)
        self.assertIs(df, src)

    def test_to_dataframe_accepts_list(self):
        df = exporter._to_dataframe(REQUIREMENTS)
        self.assertEqual(len(df), 1)
        self.assertIn("requirement_id", df.columns)

    def test_extract_test_cases_from_wrapper(self):
        cases = exporter._extract_test_cases(TEST_CASES_WRAPPER)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["test_case_id"], "TC-REQ-001-001")

    def test_extract_test_cases_from_optimizer_output(self):
        cases = exporter._extract_test_cases(
            {"optimized_test_cases": TEST_CASES_WRAPPER["test_cases"]})
        self.assertEqual(len(cases), 1)

    # --- writers ---------------------------------------------------------

    def test_export_all_produces_six_files(self):
        paths = exporter.export_all(
            requirements=REQUIREMENTS,
            risk=RISK,
            coverage=COVERAGE,
            test_cases=TEST_CASES_WRAPPER,
            output_dir=self.tmpdir,
            timestamp=self.ts,
        )
        self.assertEqual(set(paths.keys()), {
            "structured_requirements_csv",
            "risk_analysis_csv",
            "coverage_items_csv",
            "test_cases_csv",
            "test_cases_json",
            "excel",
        })
        for p in paths.values():
            self.assertTrue(os.path.exists(p), f"missing: {p}")
            self.assertGreater(os.path.getsize(p), 0, f"empty: {p}")

    def test_test_cases_json_preserves_summary(self):
        paths = exporter.export_all(
            requirements=REQUIREMENTS, risk=RISK, coverage=COVERAGE,
            test_cases=TEST_CASES_WRAPPER,
            output_dir=self.tmpdir, timestamp=self.ts,
        )
        with open(paths["test_cases_json"], encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("test_cases", data)
        self.assertIn("summary", data)
        self.assertEqual(data["summary"]["total"], 1)

    def test_test_cases_csv_serialises_nested_fields(self):
        paths = exporter.export_all(
            requirements=REQUIREMENTS, risk=RISK, coverage=COVERAGE,
            test_cases=TEST_CASES_WRAPPER,
            output_dir=self.tmpdir, timestamp=self.ts,
        )
        df = pd.read_csv(paths["test_cases_csv"], encoding="utf-8-sig")
        self.assertEqual(len(df), 1)
        # nested dict/list fields must be JSON strings, not Python reprs
        self.assertTrue(df.loc[0, "test_data"].startswith("{"))
        self.assertIn("product_id", df.loc[0, "test_data"])
        self.assertTrue(df.loc[0, "steps"].startswith("["))

    def test_excel_has_four_sheets(self):
        paths = exporter.export_all(
            requirements=REQUIREMENTS, risk=RISK, coverage=COVERAGE,
            test_cases=TEST_CASES_WRAPPER,
            output_dir=self.tmpdir, timestamp=self.ts,
        )
        sheets = pd.read_excel(paths["excel"], sheet_name=None,
                               engine="openpyxl")
        self.assertEqual(set(sheets.keys()),
                         {"Requirements", "Risk Analysis", "Coverage Items",
                          "Test Cases"})
        self.assertEqual(len(sheets["Test Cases"]), 1)

    def test_filename_uses_provided_timestamp(self):
        paths = exporter.export_all(
            requirements=REQUIREMENTS, risk=RISK, coverage=COVERAGE,
            test_cases=TEST_CASES_WRAPPER,
            output_dir=self.tmpdir, timestamp=self.ts,
        )
        for p in paths.values():
            self.assertIn(self.ts, os.path.basename(p))

    def test_empty_inputs_are_tolerated(self):
        paths = exporter.export_all(
            requirements=None,
            risk=[],
            coverage=pd.DataFrame(),
            test_cases={"test_cases": []},
            output_dir=self.tmpdir, timestamp=self.ts,
        )
        for p in paths.values():
            self.assertTrue(os.path.exists(p))


if __name__ == "__main__":
    unittest.main()
