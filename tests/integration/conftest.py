"""
conftest.py  --  shared pytest fixtures for the integration suite

The data-driven harness needs:
  1. A live target backend at backend_base_url
  2. A path to the latest generated test-cases JSON

Both are provided as fixtures so the same machinery serves both the hand-
written `test_mini_ecommerce_api.py` and the generated harness in
`test_data_driven_orders.py`.

If the backend is not reachable the integration tests are skipped (not
failed) so unit tests can still run in CI without a Django process.
"""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BASE_URL = "http://127.0.0.1:8000/api"


# ---------------------------------------------------------------------------
# Backend fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def backend_base_url() -> str:
    """Base URL the integration tests target.

    Override with the BACKEND_BASE_URL environment variable.
    """
    return os.getenv("BACKEND_BASE_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="session")
def backend_available(backend_base_url: str) -> bool:
    """True iff the target backend responds within 1s on GET /products/."""
    try:
        import requests
    except ImportError:
        return False
    try:
        r = requests.get(f"{backend_base_url}/products/", timeout=1.0)
        return r.status_code < 500
    except Exception:
        return False


@pytest.fixture(autouse=False)
def require_backend(backend_available: bool) -> None:
    """Skip the test if the target backend is not reachable."""
    if not backend_available:
        pytest.skip(
            "Mini-E-Commerce backend is not reachable. Start it with "
            "`python manage.py runserver` and retry.")


# ---------------------------------------------------------------------------
# Generated test-cases discovery
# ---------------------------------------------------------------------------

def _find_latest_outputs_test_cases() -> Path | None:
    """Return the newest outputs/test_cases_*.json, or None if missing."""
    pattern = str(PROJECT_ROOT / "outputs" / "test_cases_*.json")
    paths = sorted(glob.glob(pattern))
    return Path(paths[-1]) if paths else None


def _load_test_cases_payload(path: Path) -> List[Dict[str, Any]]:
    """Return the flat list of test_case dicts from a generator/optimiser file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("test_cases", "optimized_test_cases"):
            cases = data.get(key)
            if isinstance(cases, list):
                return [d for d in cases if isinstance(d, dict)]
    return []


@pytest.fixture(scope="session")
def generated_test_cases_path() -> Path:
    """Path the data-driven harness reads from.

    Resolution order:
      1. GENERATED_TEST_CASES env var (explicit override) — typical use:
         `GENERATED_TEST_CASES=outputs/test_cases_<ts>.json pytest -v`
      2. data/baseline/test_cases.json  (always present in the repo, schema v1)

    The baseline is preferred over any outputs/test_cases_*.json by default so
    that legacy schema files from earlier app.py versions don't silently
    pollute the data-driven harness. Use the env var to point at a fresh
    Streamlit export when you want to demo the end-to-end loop.
    """
    explicit = os.getenv("GENERATED_TEST_CASES")
    if explicit:
        return Path(explicit)

    return PROJECT_ROOT / "data" / "baseline" / "test_cases.json"


@pytest.fixture(scope="session")
def generated_test_cases(generated_test_cases_path: Path
                          ) -> List[Dict[str, Any]]:
    """The list of generated test-case dicts available to parametrise tests."""
    if not generated_test_cases_path.exists():
        return []
    return _load_test_cases_payload(generated_test_cases_path)
