"""
optimizer.py  --  B part: Test Suite Optimization

Two complementary operations on the test cases produced by
testcase_generator.py:

1. prioritize_test_cases(test_cases)
   Stable ordering by risk and black-box technique importance, so the most
   valuable cases run first.

2. minimize_test_suite(test_cases, mode="risk_based")
   Risk-based reduction of the suite. The amount kept per requirement scales
   with that requirement's risk level:
       High   -> keep more (favour boundary / negative / decision-table cases)
       Medium -> keep representative cases (one per coverage type, + DT)
       Low    -> reduce duplicates, but always keep at least one case
   This reflects the standard risk-based testing principle: spend test effort
   where a defect would hurt most.

optimize_test_suite(...) is the single public entry point that ties both
together and returns an optimization summary for the report.

Risk -> priority mapping is kept identical to testcase_generator.py:
    High -> High, Medium -> Medium, Low -> Low.
"""

from typing import Any, Dict, List, Optional

# Technique labels (kept in sync with testcase_generator.py)
TECH_DT = "Decision Table Testing"

# ---------------------------------------------------------------------------
# Ranking tables (higher == more important == sorted earlier)
# ---------------------------------------------------------------------------

_RISK_RANK = {"high": 3, "medium": 2, "low": 1}

# boundary / negative / combination exercise the riskiest behaviour first
_TYPE_RANK = {
    "boundary": 4,
    "negative": 3,
    "combination": 3,
    "positive": 2,
    "fallback": 1,
    "unknown": 0,
}

_TECH_RANK = {
    "Decision Table Testing": 3,
    "Boundary Value Analysis": 2,
    "Equivalence Partitioning": 1,
    "Manual Review": 0,
}

_RISK_TO_PRIORITY = {"high": "High", "medium": "Medium", "low": "Low"}


def _risk_to_priority(risk_level: Any) -> str:
    return _RISK_TO_PRIORITY.get(str(risk_level).strip().lower(), "Medium")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------

def _extract_test_cases(test_case_json: Any) -> List[Dict[str, Any]]:
    """Accept either a bare list or {"test_cases": [...]}."""
    if test_case_json is None:
        return []
    if isinstance(test_case_json, list):
        return [tc for tc in test_case_json if isinstance(tc, dict)]
    if isinstance(test_case_json, dict):
        cases = test_case_json.get("test_cases", [])
        if isinstance(cases, list):
            return [tc for tc in cases if isinstance(tc, dict)]
    return []


def _build_risk_index(risk_json: Any) -> Dict[str, Dict[str, Any]]:
    """requirement_id -> {risk_level, risk_score}; tolerates None/list/dict."""
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
            "risk_level": entry.get("risk_level", "Medium"),
            "risk_score": entry.get("risk_score", 5),
        }
    return index


def _apply_risk_overrides(test_cases: List[Dict[str, Any]],
                          risk_index: Dict[str, Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    """Refresh risk_level / risk_score / priority on each case from the risk
    index when available. Cases are copied so the caller's input is untouched.
    """
    out: List[Dict[str, Any]] = []
    for tc in test_cases:
        tc = dict(tc)
        rid = str(tc.get("requirement_id", ""))
        if rid in risk_index:
            tc["risk_level"] = risk_index[rid]["risk_level"]
            tc["risk_score"] = risk_index[rid]["risk_score"]
        tc["priority"] = _risk_to_priority(tc.get("risk_level"))
        out.append(tc)
    return out


# ---------------------------------------------------------------------------
# Prioritisation
# ---------------------------------------------------------------------------

def _sort_key(tc: Dict[str, Any]):
    """Sort descending: risk_level, then risk_score, then technique, then type."""
    risk = _RISK_RANK.get(str(tc.get("risk_level", "")).strip().lower(), 0)
    score = _as_int(tc.get("risk_score", 0))
    tech = _TECH_RANK.get(tc.get("test_design_technique", ""), 0)
    ctype = _TYPE_RANK.get(str(tc.get("coverage_type", "")).strip().lower(), 0)
    return (risk, score, tech, ctype)


def prioritize_test_cases(test_cases: List[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
    """Return a new list ordered by importance (most important first).

    Order of significance: risk level -> risk score -> technique -> type.
    Python's sort is stable, so cases that tie keep their original order.
    """
    cases = _extract_test_cases(test_cases)
    return sorted(cases, key=_sort_key, reverse=True)


# ---------------------------------------------------------------------------
# Minimisation
# ---------------------------------------------------------------------------

def _dedupe_by_type(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first case seen for each coverage_type (already prioritised)."""
    seen = set()
    kept = []
    for tc in cases:
        ctype = str(tc.get("coverage_type", "")).strip().lower()
        if ctype not in seen:
            seen.add(ctype)
            kept.append(tc)
    return kept


def _minimize_group(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Risk-based reduction for the cases of a single requirement.

    The group's risk level is taken as the strongest risk_level present.
    High   -> keep everything (maximum coverage where risk is highest)
    Medium -> keep one representative per coverage_type, always keep DT cases
    Low    -> keep one representative per coverage_type, at least one case
    """
    if not cases:
        return []

    # prioritise within the group first so "the first per type" is the best one
    ordered = sorted(cases, key=_sort_key, reverse=True)

    group_risk = max(
        (_RISK_RANK.get(str(c.get("risk_level", "")).strip().lower(), 0)
         for c in ordered),
        default=0)

    if group_risk >= 3:  # High -> keep more
        return ordered

    if group_risk == 2:  # Medium -> representative per type + all DT cases
        dt = [c for c in ordered
              if c.get("test_design_technique") == TECH_DT]
        rep = _dedupe_by_type(ordered)
        # union while preserving prioritised order
        kept_ids = set()
        result = []
        for c in ordered:
            if c in rep or c in dt:
                key = id(c)
                if key not in kept_ids:
                    kept_ids.add(key)
                    result.append(c)
        return result if result else ordered[:1]

    # Low -> reduce duplicates, keep one per type, guarantee >= 1
    reduced = _dedupe_by_type(ordered)
    return reduced if reduced else ordered[:1]


def minimize_test_suite(test_cases: List[Dict[str, Any]],
                        mode: str = "risk_based") -> List[Dict[str, Any]]:
    """Reduce the suite, guaranteeing every requirement keeps >= 1 case.

    Currently only mode="risk_based" is implemented; other modes fall back to
    returning the (prioritised) input unchanged.
    """
    cases = _extract_test_cases(test_cases)
    if mode != "risk_based":
        return prioritize_test_cases(cases)

    # group by requirement, preserving first-seen requirement order
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for tc in cases:
        rid = str(tc.get("requirement_id", "UNKNOWN"))
        if rid not in groups:
            groups[rid] = []
            order.append(rid)
        groups[rid].append(tc)

    minimized: List[Dict[str, Any]] = []
    for rid in order:
        kept = _minimize_group(groups[rid])
        if not kept and groups[rid]:  # safety net: never drop a whole requirement
            kept = [groups[rid][0]]
        minimized.extend(kept)

    # final global prioritisation so the minimized suite is also ordered
    return prioritize_test_cases(minimized)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def optimize_test_suite(test_case_json: Any,
                        risk_json: Any = None,
                        minimize: bool = False) -> Dict[str, Any]:
    """Optimise a test suite and return cases + an optimization summary.

    Steps:
      1. (optional) refresh each case's risk/priority from risk_json
      2. prioritise by risk + technique importance
      3. (optional) risk-based minimisation
    """
    original = _extract_test_cases(test_case_json)
    risk_index = _build_risk_index(risk_json)
    enriched = _apply_risk_overrides(original, risk_index) if risk_index else \
        [dict(tc) for tc in original]

    if minimize:
        optimized = minimize_test_suite(enriched, mode="risk_based")
        strategy = "risk_based_minimization"
    else:
        optimized = prioritize_test_cases(enriched)
        strategy = "risk_based_prioritization"

    original_count = len(original)
    optimized_count = len(optimized)

    return {
        "optimized_test_cases": optimized,
        "optimization_summary": {
            "original_count": original_count,
            "optimized_count": optimized_count,
            "strategy": strategy,
            "removed_count": max(original_count - optimized_count, 0),
        },
    }


# ---------------------------------------------------------------------------
# Manual smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.testcase_generator import generate_test_cases

    here = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(here, "..", "data")
    with open(os.path.join(data_dir, "sample_coverage.json"), encoding="utf-8") as f:
        cov = json.load(f)
    with open(os.path.join(data_dir, "sample_risk_analysis.json"), encoding="utf-8") as f:
        risk = json.load(f)

    suite = generate_test_cases(cov, risk)
    result = optimize_test_suite(suite, risk, minimize=True)
    print(json.dumps(result, indent=2, ensure_ascii=False))
