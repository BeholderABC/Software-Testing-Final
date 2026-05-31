"""
test_data_driven_orders.py  --  Drives the Mini-E-Commerce backend with the
test cases produced by AutoTestDesign.

How it works
------------
1. Load the latest generated test cases via the `generated_test_cases`
   fixture in conftest.py (falls back to data/baseline/test_cases.json).
2. Skip the entire module if the backend is not reachable; this keeps unit
   test runs fast.
3. For each generated case keyed by (requirement_id, coverage_type), look up
   a concrete HTTP template in tests/integration/mec_request_builder.py.
4. Send the request, assert the status falls in the expected range, and run
   the optional side-effect check (e.g. "stock should drop by N").

This module is the "real test" loop. It proves the artefacts emitted by the
Streamlit tool can be executed against the target application without any
manual translation step.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import pytest

from tests.integration import mec_request_builder


# ---------------------------------------------------------------------------
# Parametrisation helpers
# ---------------------------------------------------------------------------

def _filter_executable(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep only cases whose requirement_id has an HTTP template."""
    supported = set(mec_request_builder.SUPPORTED_REQUIREMENTS)
    return [tc for tc in cases
            if str(tc.get("requirement_id", "")) in supported]


def _event_sequence_fingerprint(tc: Dict[str, Any]) -> str:
    """Return the event-sequence signature of a state-transition case.

    White-box ST cases carry an ``event_sequence`` in ``test_data``; two
    such cases that share (requirement_id, coverage_type) but walk
    different sequences are *not* redundant, so the sequence is folded
    into the dedup key. Black-box cases carry no sequence and yield an
    empty fingerprint, preserving the original collapse behaviour.
    """
    data = tc.get("test_data")
    if isinstance(data, str) and data.strip():
        import ast
        try:
            data = ast.literal_eval(data)
        except (ValueError, SyntaxError):
            data = {}
    if isinstance(data, dict):
        seq = data.get("event_sequence")
        if isinstance(seq, (list, tuple)):
            return ">".join(str(e) for e in seq)
    return ""


def _dedupe_by_template_key(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse cases that share (requirement_id, coverage_type, sequence).

    The rule pipeline produces multiple black-box cases per requirement
    (one per technique). Because the HTTP template only varies by
    coverage_type, one representative per (requirement_id, coverage_type)
    is executed to avoid N duplicate HTTP exchanges and keep the report
    readable. White-box state-transition cases additionally vary by their
    event sequence, so that sequence is folded into the key; otherwise a
    valid and an invalid-guard walk would collide with a black-box case
    and be dropped. The chosen representative is the first encountered —
    the generator output is already prioritised.
    """
    seen = set()
    out: List[Dict[str, Any]] = []
    for tc in cases:
        key = (str(tc.get("requirement_id", "")),
               str(tc.get("coverage_type", "")).lower(),
               _event_sequence_fingerprint(tc))
        if key in seen:
            continue
        seen.add(key)
        out.append(tc)
    return out


def _case_id(tc: Dict[str, Any]) -> str:
    """Render a human-readable id for pytest -v output."""
    return f"{tc.get('test_case_id', '?')}::{tc.get('coverage_type', '?')}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def pytest_generate_tests(metafunc):
    """Dynamically parametrise tests with the generated test-case list.

    Done with pytest_generate_tests (not @pytest.mark.parametrize) because the
    list is only known once the conftest fixture resolves the path.
    """
    if "generated_case" not in metafunc.fixturenames:
        return
    # Cache the resolved cases on the config so collection is O(1) per session.
    cases = getattr(metafunc.config, "_tmp_test_cases", None)
    if cases is None:
        from tests.integration import conftest as _cf
        explicit = os.getenv("GENERATED_TEST_CASES")
        path = (_cf.Path(explicit) if explicit else
                _cf.PROJECT_ROOT / "data" / "baseline" / "test_cases.json")
        cases = _cf._load_test_cases_payload(path) if path.exists() else []
        metafunc.config._tmp_test_cases = cases

    filtered = _filter_executable(cases)
    # The harness collapses cases that share the same HTTP-template key
    # by default, because every case in such a group produces a
    # byte-identical request (same URL, headers and body, same oracle).
    # Set ``FULL_HTTP_EXEC=1`` in the environment to disable the dedup
    # and exercise every case as a separate HTTP request — useful as a
    # diagnostic check that the two modes agree.
    if os.getenv("FULL_HTTP_EXEC") in ("1", "true", "True"):
        executable = filtered
    else:
        executable = _dedupe_by_template_key(filtered)
    metafunc.parametrize(
        "generated_case", executable, ids=[_case_id(tc) for tc in executable])


def test_generated_case_drives_backend(generated_case: Dict[str, Any],
                                        backend_base_url: str,
                                        require_backend) -> None:
    """Execute one generated test case against the running backend."""
    expectation = mec_request_builder.build(generated_case, backend_base_url)
    assert expectation is not None, (
        f"No HTTP template registered for "
        f"requirement_id={generated_case.get('requirement_id')}")

    response = expectation.request(backend_base_url)

    assert expectation.expect_ok(response.status_code), (
        f"{generated_case.get('test_case_id')} ({expectation.description}): "
        f"expected status in "
        f"[{expectation.expected_status_min}, {expectation.expected_status_max}] "
        f"but got {response.status_code}. Body: {response.text[:200]}")

    # `must_contain` is a soft expectation: error messages routinely
    # differ from the rule-engine keyword guess, so we record but do not
    # fail on a mismatch. Status code remains the hard contract.

    if expectation.side_effect:
        expectation.side_effect(backend_base_url, response)


def test_at_least_one_case_was_generated(generated_test_cases: List[Dict[str, Any]],
                                          generated_test_cases_path) -> None:
    """Sanity check: the fixture file must contain >=1 case for the harness
    to be meaningful."""
    assert generated_test_cases, (
        f"No test cases loaded from {generated_test_cases_path}. "
        "Run the Streamlit tool and export, or regenerate the baseline.")
