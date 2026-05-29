"""
exporter.py  --  C part: Export Test Artifacts

Single source of truth for writing AutoTestDesign pipeline output into the
formats third-party test management tools can consume:

    - structured_requirements_{ts}.csv
    - risk_analysis_{ts}.csv
    - coverage_items_{ts}.csv
    - test_cases_{ts}.csv
    - test_cases_{ts}.json
    - AutoTestDesign_Output_{ts}.xlsx  (multi-sheet workbook)

The module accepts both pandas DataFrame and plain list-of-dicts input so that
Streamlit (uses DataFrame) and back-end pipelines (use raw JSON from core/)
can share the same exporter.

All CSV files are written with UTF-8 BOM (`utf-8-sig`) so Excel opens them
without mojibake.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd


# ---------------------------------------------------------------------------
# Type aliases & constants
# ---------------------------------------------------------------------------

TableLike = Union[pd.DataFrame, List[Dict[str, Any]]]
JSONLike = Union[Dict[str, Any], List[Dict[str, Any]]]

DEFAULT_OUTPUT_DIR = "outputs"


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

def _to_dataframe(data: TableLike) -> pd.DataFrame:
    """Coerce a DataFrame or list-of-dicts into a DataFrame.

    Tolerates None / empty inputs by returning an empty DataFrame so the
    downstream CSV / Excel writers do not blow up on optional pipelines.
    """
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data
    if isinstance(data, list):
        return pd.DataFrame(data)
    raise TypeError(
        "Unsupported export input type: {t}".format(t=type(data).__name__))


def _extract_test_cases(test_cases: Union[TableLike, JSONLike]) -> List[Dict[str, Any]]:
    """Pull a flat list of test case dicts out of any supported shape.

    Accepted inputs:
      - pandas DataFrame (one row per test case)
      - list of test case dicts
      - {"test_cases": [...]}  (testcase_generator output)
      - {"optimized_test_cases": [...]}  (optimizer output)
    """
    if test_cases is None:
        return []
    if isinstance(test_cases, pd.DataFrame):
        return test_cases.to_dict(orient="records")
    if isinstance(test_cases, list):
        return [tc for tc in test_cases if isinstance(tc, dict)]
    if isinstance(test_cases, dict):
        for key in ("test_cases", "optimized_test_cases"):
            cases = test_cases.get(key)
            if isinstance(cases, list):
                return [tc for tc in cases if isinstance(tc, dict)]
    return []


# ---------------------------------------------------------------------------
# Single-artifact writers
# ---------------------------------------------------------------------------

def export_requirements_csv(requirements: TableLike, path: str) -> str:
    """Write structured requirements to a UTF-8 BOM CSV. Returns the path."""
    _to_dataframe(requirements).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_risk_csv(risk: TableLike, path: str) -> str:
    """Write the risk analysis table to a UTF-8 BOM CSV. Returns the path."""
    _to_dataframe(risk).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_coverage_csv(coverage: TableLike, path: str) -> str:
    """Write coverage items to a UTF-8 BOM CSV. Returns the path."""
    _to_dataframe(coverage).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_test_cases_csv(test_cases: Union[TableLike, JSONLike],
                          path: str) -> str:
    """Write test cases to a UTF-8 BOM CSV. Returns the path.

    Nested fields (test_data / traceability / oracle) are JSON-serialised so
    they survive the CSV round-trip.
    """
    cases = _extract_test_cases(test_cases)
    df = pd.DataFrame(cases)
    for col in ("test_data", "traceability", "oracle", "steps",
                "preconditions"):
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: json.dumps(v, ensure_ascii=False) if isinstance(
                    v, (dict, list)) else v)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_test_cases_json(test_cases: Union[TableLike, JSONLike],
                           path: str,
                           include_summary: bool = True) -> str:
    """Write test cases (and optional summary) to a JSON file. Returns path.

    When include_summary is True and the input is a dict containing both
    "test_cases" and "summary", the original wrapper is preserved.
    """
    if include_summary and isinstance(test_cases, dict) and \
            "test_cases" in test_cases:
        payload = test_cases
    else:
        payload = _extract_test_cases(test_cases)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def export_excel(sheets: Dict[str, TableLike], path: str) -> str:
    """Write multiple DataFrames into one Excel workbook.

    `sheets` maps sheet name -> table-like input (DataFrame or list-of-dicts).
    Returns the path. Empty sheets are still created so the workbook layout is
    predictable.
    """
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, data in sheets.items():
            df = _to_dataframe(data)
            # Excel limits sheet names to 31 characters
            safe_name = str(sheet_name)[:31] or "Sheet"
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return path


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def build_timestamp() -> str:
    """Return a YYYYMMDD_HHMMSS timestamp matching the existing outputs/."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_all(requirements: TableLike,
               risk: TableLike,
               coverage: TableLike,
               test_cases: Union[TableLike, JSONLike],
               output_dir: str = DEFAULT_OUTPUT_DIR,
               timestamp: Optional[str] = None) -> Dict[str, str]:
    """Write the full set of artefacts and return a {kind: path} dict.

    Keys returned (mirrors the historical Streamlit naming for compatibility):
        - structured_requirements_csv
        - risk_analysis_csv
        - coverage_items_csv
        - test_cases_csv
        - test_cases_json
        - excel
    """
    os.makedirs(output_dir, exist_ok=True)
    ts = timestamp or build_timestamp()

    paths = {
        "structured_requirements_csv": os.path.join(
            output_dir, f"structured_requirements_{ts}.csv"),
        "risk_analysis_csv": os.path.join(
            output_dir, f"risk_analysis_{ts}.csv"),
        "coverage_items_csv": os.path.join(
            output_dir, f"coverage_items_{ts}.csv"),
        "test_cases_csv": os.path.join(
            output_dir, f"test_cases_{ts}.csv"),
        "test_cases_json": os.path.join(
            output_dir, f"test_cases_{ts}.json"),
        "excel": os.path.join(
            output_dir, f"AutoTestDesign_Output_{ts}.xlsx"),
    }

    export_requirements_csv(requirements, paths["structured_requirements_csv"])
    export_risk_csv(risk, paths["risk_analysis_csv"])
    export_coverage_csv(coverage, paths["coverage_items_csv"])
    export_test_cases_csv(test_cases, paths["test_cases_csv"])
    export_test_cases_json(test_cases, paths["test_cases_json"])

    export_excel(
        sheets={
            "Requirements": requirements,
            "Risk Analysis": risk,
            "Coverage Items": coverage,
            "Test Cases": _extract_test_cases(test_cases),
        },
        path=paths["excel"],
    )

    return paths


# ---------------------------------------------------------------------------
# Manual smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_paths = export_all(
        requirements=[{"requirement_id": "REQ-001", "raw_requirement": "demo"}],
        risk=[{"requirement_id": "REQ-001", "risk_level": "Medium",
               "risk_score": 5}],
        coverage=[{"coverage_item_id": "CI-001", "requirement_id": "REQ-001",
                   "coverage_strategy": "Equivalence Partitioning",
                   "priority": "Medium"}],
        test_cases={
            "test_cases": [{
                "test_case_id": "TC-REQ-001-001",
                "requirement_id": "REQ-001",
                "test_design_technique": "Equivalence Partitioning",
                "test_data": {"x": 1},
                "traceability": {"source_requirement": "REQ-001"},
            }],
            "summary": {"total": 1},
        },
        output_dir="outputs/_exporter_smoke",
    )
    for k, v in sample_paths.items():
        print(f"{k}: {v}")
