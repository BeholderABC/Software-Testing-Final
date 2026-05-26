"""
testcase_generator.py  --  B part: Test Design Engine (rule-driven, no LLM)

This module turns *coverage items* (produced by the A-part coverage_analysis.py)
into structured, traceable black-box test cases. It does NOT call any LLM; all
decisions are made by a deterministic rule engine so the output is reproducible
and easy to cite in the report.

Black-box techniques applied
-----------------------------
- Equivalence Partitioning (EP)   -> coverage_type positive / negative
- Boundary Value Analysis (BVA)   -> coverage_type boundary
- Decision Table Testing (DT)     -> requirements with several coverage items
- Manual review fallback          -> coverage_type fallback / unknown

Traceability
------------
Every test case keeps a `traceability` block linking it back to its source
requirement and the exact coverage item it was derived from, so the chain
    requirement -> coverage item -> test case
is always reconstructable.

Risk -> priority mapping
------------------------
    High   -> High
    Medium -> Medium
    Low    -> Low
If no risk info is available for a requirement we fall back to
risk_level="Medium", risk_score=5, priority="Medium".
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Technique / priority constants
# ---------------------------------------------------------------------------

TECH_EP = "Equivalence Partitioning"
TECH_BVA = "Boundary Value Analysis"
TECH_DT = "Decision Table Testing"
TECH_MANUAL = "Manual Review"

# risk_level -> priority is a direct 1:1 mapping in this project
_RISK_TO_PRIORITY = {"high": "High", "medium": "Medium", "low": "Low"}

_DEFAULT_RISK = {"risk_level": "Medium", "risk_score": 5}


# ---------------------------------------------------------------------------
# Input normalisation helpers
# ---------------------------------------------------------------------------

def _extract_coverage_groups(coverage_json: Any) -> List[Dict[str, Any]]:
    """Return the list of coverage groups, tolerating several input shapes.

    Accepts:
      - {"coverages": [...]}   (schema doc spelling)
      - {"coverage":  [...]}   (sample_coverage.json spelling)
      - a bare list of groups
    """
    if coverage_json is None:
        return []
    if isinstance(coverage_json, list):
        return [g for g in coverage_json if isinstance(g, dict)]
    if isinstance(coverage_json, dict):
        groups = coverage_json.get("coverages")
        if groups is None:
            groups = coverage_json.get("coverage")
        if isinstance(groups, list):
            return [g for g in groups if isinstance(g, dict)]
    return []


def _build_risk_index(risk_json: Any) -> Dict[str, Dict[str, Any]]:
    """Map requirement_id -> {risk_level, risk_score} from a risk-analysis blob.

    Tolerates risk_json being None, a list, or {"risk_assessment": [...]}.
    """
    index: Dict[str, Dict[str, Any]] = {}
    if not risk_json:
        return index

    if isinstance(risk_json, dict):
        entries = risk_json.get("risk_assessment", [])
    elif isinstance(risk_json, list):
        entries = risk_json
    else:
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rid = entry.get("requirement_id")
        if rid is None:
            continue
        index[str(rid)] = {
            "risk_level": entry.get("risk_level", _DEFAULT_RISK["risk_level"]),
            "risk_score": entry.get("risk_score", _DEFAULT_RISK["risk_score"]),
        }
    return index


def _resolve_risk(requirement_id: str,
                  risk_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Look up risk info for a requirement, falling back to Medium/5."""
    info = risk_index.get(str(requirement_id))
    if not info:
        return dict(_DEFAULT_RISK)
    return {
        "risk_level": info.get("risk_level", _DEFAULT_RISK["risk_level"]),
        "risk_score": info.get("risk_score", _DEFAULT_RISK["risk_score"]),
    }


def _risk_to_priority(risk_level: Any) -> str:
    """Map a risk level string to a priority (High/Medium/Low)."""
    return _RISK_TO_PRIORITY.get(str(risk_level).strip().lower(), "Medium")


def _normalise_type(coverage_type: Any) -> str:
    """Lower-case, trimmed coverage type; unknown values collapse to 'unknown'."""
    if not coverage_type:
        return "unknown"
    t = str(coverage_type).strip().lower()
    if t in ("positive", "negative", "boundary", "fallback"):
        return t
    return "unknown"


def _select_technique(coverage_type: str) -> str:
    """Pick the black-box technique for a single coverage item.

    positive / negative -> Equivalence Partitioning
    boundary            -> Boundary Value Analysis
    fallback / unknown  -> Manual Review
    """
    if coverage_type in ("positive", "negative"):
        return TECH_EP
    if coverage_type == "boundary":
        return TECH_BVA
    return TECH_MANUAL


def _tc_id(requirement_id: str, index: int) -> str:
    """Build a stable, readable id like TC-R1-001."""
    return "TC-{rid}-{idx:03d}".format(rid=requirement_id, idx=index)


# ---------------------------------------------------------------------------
# Test data inference (rule engine)
# ---------------------------------------------------------------------------

def infer_test_data(description: str, coverage_type: str) -> Dict[str, Any]:
    """Derive a small, plausible test_data dict from the item description.

    The rules are intentionally simple keyword matches -- enough to show the
    rule engine produces concrete data, not to model the full domain.
    """
    desc = (description or "").strip().lower()
    ctype = _normalise_type(coverage_type)

    # ---- password rules -------------------------------------------------
    if "password" in desc or "uppercase" in desc or "lowercase" in desc or "digit" in desc:
        # explicit length, e.g. "password length = 20"
        length = _extract_length(desc)
        if length is not None:
            return {"password": _make_password(length)}
        if "missing uppercase" in desc:
            return {"password": "abc12345"}
        if "missing lowercase" in desc:
            return {"password": "ABC12345"}
        if "missing digit" in desc:
            return {"password": "Abcdefgh"}
        if "contains all" in desc or "all required" in desc:
            return {"password": "Abc12345"}
        # generic password fallback
        return {"password": "Abc12345" if ctype == "positive" else "weak"}

    # ---- username rules -------------------------------------------------
    if "username" in desc or "user name" in desc:
        if "empty" in desc or "blank" in desc:
            return {"username": ""}
        if "exist" in desc or "duplicate" in desc or "taken" in desc:
            return {"username": "existing_user"}
        if "new" in desc or "unique" in desc:
            return {"username": "new_user_001"}
        length = _extract_length(desc)
        if length is not None:
            return {"username": "u" * max(length, 0)}
        return {"username": "test_user"}

    # ---- email rules ----------------------------------------------------
    if "email" in desc or "e-mail" in desc:
        if "invalid" in desc or "malformed" in desc:
            return {"email": "invalid-email"}
        if "empty" in desc:
            return {"email": ""}
        return {"email": "user@example.com"}

    # ---- generic empty / boundary cues ----------------------------------
    if "empty" in desc or "blank" in desc:
        return {"input": ""}
    length = _extract_length(desc)
    if length is not None:
        return {"input": "x" * max(length, 0)}

    # nothing matched -> leave empty, caller may flag manual review
    return {}


def _extract_length(desc: str) -> Optional[int]:
    """Pull an integer length out of phrases like 'length = 20' or 'length 7'."""
    import re
    m = re.search(r"length\s*[=:]?\s*(\d+)", desc)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _make_password(length: int) -> str:
    """Build a password of exactly `length` chars containing an uppercase
    letter and a digit, padded with sequential lowercase letters.

    e.g. 7 -> 'A1bcdef', 8 -> 'A1bcdefg', 20 -> 20-char password.
    Only the length varies, so it is a clean boundary-value fixture.
    """
    if length <= 0:
        return ""
    prefix = "A1"  # uppercase + digit
    if length <= len(prefix):
        return prefix[:length]
    letters = []
    for i in range(length - len(prefix)):
        letters.append(chr(ord("b") + (i % 25)))  # b, c, d, ... wraps within a-z
    return prefix + "".join(letters)


# ---------------------------------------------------------------------------
# Expected result inference
# ---------------------------------------------------------------------------

def infer_expected_result(description: str, coverage_type: str) -> str:
    """Derive an expected_result string from the coverage item.

    Because the generator only sees a single coverage item (not the full
    min/max range), boundary expectations stay conservative unless the
    description clearly signals an out-of-range value such as 'length = 7'.
    """
    desc = (description or "").strip().lower()
    ctype = _normalise_type(coverage_type)

    if ctype == "positive":
        return "The system should accept the input and continue the normal flow."

    if ctype == "negative":
        return ("The system should reject the input and display a meaningful "
                "error message.")

    if ctype == "boundary":
        # Common password policy range used in this project is 8..20 chars.
        length = _extract_length(desc)
        if length is not None:
            if length < 8 or length > 20:
                return ("The system should reject this out-of-range boundary "
                        "value with a clear validation error.")
            return ("The system should accept this in-range boundary value "
                    "and continue normally.")
        if "empty" in desc or "blank" in desc:
            return ("The system should reject the empty value with a clear "
                    "validation error.")
        # min/max unknown -> conservative wording
        return ("The system should handle this boundary value according to "
                "the requirement.")

    # fallback / unknown
    return ("Expected behaviour is unclear from the coverage item -- requires "
            "manual review against the requirement.")


# ---------------------------------------------------------------------------
# Single test-case construction
# ---------------------------------------------------------------------------

def generate_test_case_for_item(requirement_id: str,
                                feature: str,
                                coverage_item: Dict[str, Any],
                                risk_info: Optional[Dict[str, Any]],
                                index: int) -> Dict[str, Any]:
    """Build one structured test case from a single coverage item.

    Implements coverage-item -> test-case traceability and applies the
    EP / BVA / Manual-Review technique selection.
    """
    if not isinstance(coverage_item, dict):
        coverage_item = {}

    description = str(coverage_item.get("description", "")).strip()
    coverage_type = _normalise_type(coverage_item.get("type"))
    technique = _select_technique(coverage_type)
    need_manual = technique == TECH_MANUAL

    risk_info = risk_info or dict(_DEFAULT_RISK)
    risk_level = risk_info.get("risk_level", _DEFAULT_RISK["risk_level"])
    risk_score = risk_info.get("risk_score", _DEFAULT_RISK["risk_score"])
    priority = _risk_to_priority(risk_level)

    coverage_strategy = {
        "positive": "positive path coverage",
        "negative": "negative path coverage",
        "boundary": "boundary value coverage",
        "fallback": "fallback / manual coverage",
        "unknown": "manual coverage",
    }[coverage_type]

    title = "Verify {desc}".format(desc=description or "behaviour")
    if need_manual:
        expected = ("Expected behaviour is unclear -- requires manual review "
                    "against the requirement.")
    else:
        expected = infer_expected_result(description, coverage_type)

    return {
        "test_case_id": _tc_id(requirement_id, index),
        "requirement_id": requirement_id,
        "feature": feature,
        "title": title,
        "description": "Test the condition: {desc}".format(
            desc=description or "(no description provided)"),
        "test_design_technique": technique,
        "coverage_item": description,
        "coverage_type": coverage_type,
        "preconditions": [],
        "test_data": infer_test_data(description, coverage_type),
        "steps": [
            "Open the target feature: {feat}".format(feat=feature),
            "Prepare test data for: {desc}".format(desc=description),
            "Execute the operation according to the requirement",
            "Observe the actual result",
        ],
        "expected_result": expected,
        "priority": priority,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "traceability": {
            "source_requirement": requirement_id,
            "covered_item": description,
            "coverage_strategy": coverage_strategy,
        },
        "review_status": "generated",
        "need_manual_review": need_manual,
    }


# ---------------------------------------------------------------------------
# Decision table cases (combination conditions)
# ---------------------------------------------------------------------------

def generate_decision_table_cases(coverage_group: Dict[str, Any],
                                  risk_info: Optional[Dict[str, Any]],
                                  start_index: int) -> List[Dict[str, Any]]:
    """Generate 1..3 Decision Table cases for a requirement that owns several
    coverage items, to exercise *combinations* of conditions.

    Strategy:
      - all valid conditions satisfied  -> system accepts
      - one required condition missing   -> system rejects
      - multiple invalid conditions      -> system rejects
    Only rules for which the group actually has matching items are emitted.
    If conditions cannot be inferred, a single basic case flagged for manual
    review is produced instead.
    """
    if not isinstance(coverage_group, dict):
        return []

    requirement_id = str(coverage_group.get("requirement_id", "UNKNOWN"))
    feature = str(coverage_group.get("feature", ""))
    items = coverage_group.get("coverage_items", []) or []
    items = [i for i in items if isinstance(i, dict)]

    if len(items) < 2:
        return []  # combinations need at least two conditions

    risk_info = risk_info or dict(_DEFAULT_RISK)
    risk_level = risk_info.get("risk_level", _DEFAULT_RISK["risk_level"])
    risk_score = risk_info.get("risk_score", _DEFAULT_RISK["risk_score"])
    priority = _risk_to_priority(risk_level)

    positives = [i for i in items if _normalise_type(i.get("type")) == "positive"]
    negatives = [i for i in items if _normalise_type(i.get("type")) == "negative"]

    cases: List[Dict[str, Any]] = []
    idx = start_index

    def _base_case(title: str, desc: str, conditions: List[str],
                   expected: str, manual: bool) -> Dict[str, Any]:
        return {
            "test_case_id": _tc_id(requirement_id, idx),
            "requirement_id": requirement_id,
            "feature": feature,
            "title": title,
            "description": desc,
            "test_design_technique": TECH_DT,
            "coverage_item": "; ".join(conditions),
            "coverage_type": "combination",
            "preconditions": [],
            "test_data": {},
            "steps": [
                "Open the target feature: {feat}".format(feat=feature),
                "Set up the condition combination: {c}".format(
                    c="; ".join(conditions)),
                "Execute the operation according to the requirement",
                "Observe the actual result",
            ],
            "expected_result": expected,
            "priority": priority,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "traceability": {
                "source_requirement": requirement_id,
                "covered_item": "; ".join(conditions),
                "coverage_strategy": "decision table / combination coverage",
            },
            "review_status": "generated",
            "need_manual_review": manual,
        }

    # Rule 1: all valid conditions satisfied -> accept
    if positives:
        conds = [str(p.get("description", "")) for p in positives]
        cases.append(_base_case(
            title="Decision Table: all required conditions satisfied",
            desc="All valid conditions are satisfied simultaneously.",
            conditions=conds,
            expected="The system should accept the input and continue the "
                     "normal flow.",
            manual=False))
        idx += 1

    # Rule 2: exactly one required condition missing -> reject
    if negatives:
        conds = [str(negatives[0].get("description", ""))]
        cases.append(_base_case(
            title="Decision Table: one required condition missing",
            desc="Exactly one required condition is violated.",
            conditions=conds,
            expected="The system should reject the input and report the "
                     "violated condition.",
            manual=False))
        idx += 1

    # Rule 3: multiple invalid conditions -> reject
    if len(negatives) >= 2:
        conds = [str(n.get("description", "")) for n in negatives[:3]]
        cases.append(_base_case(
            title="Decision Table: multiple invalid conditions",
            desc="Several conditions are violated at the same time.",
            conditions=conds,
            expected="The system should reject the input and report at least "
                     "one validation error.",
            manual=False))
        idx += 1

    # Could not infer any combination -> basic case flagged for manual review
    if not cases:
        conds = [str(i.get("description", "")) for i in items[:3]]
        cases.append(_base_case(
            title="Decision Table: basic combination (needs review)",
            desc="Combination conditions could not be inferred automatically.",
            conditions=conds,
            expected="Expected behaviour for this combination requires manual "
                     "review against the requirement.",
            manual=True))

    return cases[:3]  # never emit more than 3 DT cases per requirement


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def build_summary(test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate counts by technique and by priority for the report."""
    by_technique: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}

    for tc in test_cases:
        tech = tc.get("test_design_technique", "Unknown")
        prio = tc.get("priority", "Medium")
        by_technique[tech] = by_technique.get(tech, 0) + 1
        by_priority[prio] = by_priority.get(prio, 0) + 1

    return {
        "total": len(test_cases),
        "by_technique": by_technique,
        "by_priority": by_priority,
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def generate_test_cases(coverage_json: Any,
                        risk_json: Any = None) -> Dict[str, Any]:
    """Generate the full test suite from coverage + (optional) risk JSON.

    Returns {"test_cases": [...], "summary": {...}}.

    For each requirement group:
      1. one EP/BVA/Manual case per coverage item, then
      2. up to 3 Decision Table cases if the group has multiple items.
    Test-case ids are sequential *within* each requirement (TC-R1-001, ...).
    """
    groups = _extract_coverage_groups(coverage_json)
    risk_index = _build_risk_index(risk_json)

    test_cases: List[Dict[str, Any]] = []

    for group in groups:
        requirement_id = str(group.get("requirement_id", "UNKNOWN"))
        feature = str(group.get("feature", ""))
        items = group.get("coverage_items", []) or []
        items = [i for i in items if isinstance(i, dict)]

        risk_info = _resolve_risk(requirement_id, risk_index)

        index = 1
        for item in items:
            test_cases.append(generate_test_case_for_item(
                requirement_id, feature, item, risk_info, index))
            index += 1

        # decision table cases continue the same id sequence
        dt_cases = generate_decision_table_cases(group, risk_info, index)
        test_cases.extend(dt_cases)

    return {
        "test_cases": test_cases,
        "summary": build_summary(test_cases),
    }


# ---------------------------------------------------------------------------
# Manual smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(here, "..", "data")
    with open(os.path.join(data_dir, "sample_coverage.json"), encoding="utf-8") as f:
        cov = json.load(f)
    risk_path = os.path.join(data_dir, "sample_risk_analysis.json")
    risk = None
    if os.path.exists(risk_path):
        with open(risk_path, encoding="utf-8") as f:
            risk = json.load(f)

    result = generate_test_cases(cov, risk)
    print(json.dumps(result, indent=2, ensure_ascii=False))
