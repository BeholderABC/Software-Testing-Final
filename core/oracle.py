"""
oracle.py  --  Structured test-oracle synthesis (FR 5.0)

Given a coverage item, a coverage type, and the structured requirement
it belongs to, this module derives a machine-checkable expectation:

    {
      "http_status_min": 200,
      "http_status_max": 201,
      "must_contain": [],
      "must_not_contain": [],
      "side_effect": {}
    }

The test-case generator and the data-driven harness can then assert
against an unambiguous expected outcome instead of parsing free-text.

Design rules
------------
- Positive cases assume 2xx (200-201) by default.
- Negative cases assume 4xx (400) by default.
- Boundary cases that the description marks as "out of range / 0 / >
  stock" are treated as negatives (400). Boundary values that fall
  inside the allowed window are treated as positives (201).
- `must_contain` is filled with keywords lifted from the requirement's
  `expected_behavior` field when the case is meant to be rejected; this
  lets the harness assert that the error message names the violated
  rule.

No LLM call. Same input → same oracle, so the generation is fully
reproducible.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# coverage_type → default HTTP outcome window
_DEFAULT_WINDOW: Dict[str, tuple] = {
    "positive": (200, 201),
    "negative": (400, 400),
    "boundary": (400, 400),       # most boundary failures are 400
    "combination": (400, 400),
    "fallback": (200, 499),
    "unknown": (200, 499),
}

# Keywords whose presence in the coverage item or description means
# "this boundary value is *inside* the allowed range" (200/201 expected).
_BOUNDARY_OK_HINTS = (
    "equal to stock", "= stock", "in-range", "within range",
    "lower valid", "upper valid", "valid boundary",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def derive_oracle(coverage_item: str,
                  coverage_type: str,
                  requirement: Optional[Dict[str, Any]] = None,
                  expected_result: str = "") -> Dict[str, Any]:
    """Synthesise a structured oracle for one test case.

    Parameters
    ----------
    coverage_item
        The "what is being verified" string emitted by the coverage
        engine (e.g. ``"Boundary validation for quantity > stock"``).
    coverage_type
        positive / negative / boundary / combination / fallback / unknown.
    requirement
        Optional parsed requirement dict (the same shape as in
        ``data/mini_ecommerce_requirements.json``). Used to lift keywords
        out of ``expected_behavior`` for ``must_contain``.
    expected_result
        Free-text expected result from the test case (if any). Inspected
        as an extra signal for the "boundary inside range" hint.
    """
    ctype = (coverage_type or "").strip().lower()
    text = " ".join([coverage_item or "", expected_result or ""]).lower()

    lo, hi = _DEFAULT_WINDOW.get(ctype, (200, 499))

    # Boundary fix-up: some boundary cases are actually valid inputs.
    if ctype == "boundary":
        if any(h in text for h in _BOUNDARY_OK_HINTS):
            lo, hi = 200, 201
        elif "= 0" in text or "zero" in text or "exceeds" in text \
                or "> stock" in text or "negative" in text:
            lo, hi = 400, 400

    must_contain: List[str] = []
    must_not_contain: List[str] = []
    if requirement and lo >= 400:
        must_contain = _keywords_from_requirement(requirement)

    return {
        "http_status_min": lo,
        "http_status_max": hi,
        "must_contain": must_contain,
        "must_not_contain": must_not_contain,
        "side_effect": {},
    }


def attach_oracles(test_cases: List[Dict[str, Any]],
                   requirements: Optional[List[Dict[str, Any]]] = None
                   ) -> List[Dict[str, Any]]:
    """Mutate the test cases in-place, adding an `oracle` field to each.

    Returns the same list for chaining. Idempotent: existing oracle
    fields are preserved (so a designer can hand-tune one and regenerate
    the rest).
    """
    req_index = _index_requirements(requirements or [])
    for tc in test_cases:
        if tc.get("oracle"):
            continue
        rid = str(tc.get("requirement_id", ""))
        tc["oracle"] = derive_oracle(
            coverage_item=str(tc.get("coverage_item", "")),
            coverage_type=str(tc.get("coverage_type", "")),
            requirement=req_index.get(rid),
            expected_result=str(tc.get("expected_result", "")),
        )
    return test_cases


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "of", "with", "to", "for", "and", "or", "if",
    "is", "are", "be", "system", "shall", "must", "should", "returns",
    "return", "request", "user", "customer", "order", "product",
    "into", "than", "via", "this", "that", "by", "on", "in", "at",
    "as", "from", "when", "exceeds",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z_]+")


def _keywords_from_requirement(req: Dict[str, Any]) -> List[str]:
    """Pick up to three salient lowercase keywords from expected_behavior.

    A defensive heuristic: rank words by length descending (longer words
    tend to be domain-specific) after dropping stopwords.
    """
    text = " ".join(req.get("expected_behavior", []) or []).lower()
    words = [w for w in _WORD_RE.findall(text)
             if w not in _STOPWORDS and len(w) > 3]
    # de-dupe, preserve order; rank by descending length for salience
    seen = set()
    ranked: List[str] = []
    for w in sorted(words, key=lambda x: -len(x)):
        if w in seen:
            continue
        seen.add(w)
        ranked.append(w)
    return ranked[:3]


def _index_requirements(requirements: List[Dict[str, Any]]
                         ) -> Dict[str, Dict[str, Any]]:
    return {str(r.get("requirement_id", "")): r for r in requirements
            if r.get("requirement_id")}


# Manual smoke test
if __name__ == "__main__":
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    with open(root / "data" / "baseline" / "test_cases.json",
              encoding="utf-8") as f:
        cases = json.load(f)["test_cases"]
    with open(root / "data" / "mini_ecommerce_requirements.json",
              encoding="utf-8") as f:
        reqs = json.load(f)["requirements"]

    attach_oracles(cases, reqs)
    for tc in cases[:6]:
        print(tc["test_case_id"], "::", tc["coverage_type"], "->", tc["oracle"])
