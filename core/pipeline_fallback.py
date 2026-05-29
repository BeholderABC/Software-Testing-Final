"""
Deterministic rule pipeline used when no LLM is configured.

The Streamlit UI prefers the LLM nodes in `core/parser.py` and
`core/risk_analysis.py`. When the API key is missing or the call fails
the UI silently falls back to this module so the demo never breaks
because of network or quota issues.

Output shapes are identical to the LLM path: parsed requirements follow
the schema v1 documented in `docs/STYLE_GUIDE.md`, so the downstream
pipeline (coverage / test case generation / optimisation / export) does
not need to know which path produced them.

The rules are intentionally simple keyword matches; they exist to keep
the demo running rather than to model the full domain. The LLM path
remains the primary source of structured data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Stage 1 — text → structured requirements
# ---------------------------------------------------------------------------

_REQ_ID_RE = re.compile(r"^([A-Z]+-\d+)\s*[:\-]\s*(.+)$")


def parse_requirements_struct(raw_text: str) -> Dict[str, Any]:
    """Parse free-text requirements into the schema-v1 JSON shape.

    The returned dict is `{"requirements": [...]}`. Each entry carries
    `requirement_id`, `feature`, `inputs`, `constraints`, `conditions`,
    `expected_behavior` and `target_module`. The fallback constraint
    inference uses keyword heuristics to keep boundary / negative
    coverage generation meaningful even without an LLM.
    """
    requirements: List[Dict[str, Any]] = []
    auto_index = 0

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = _REQ_ID_RE.match(line)
        if match:
            req_id, sentence = match.group(1).strip(), match.group(2).strip()
        else:
            auto_index += 1
            req_id = f"REQ-{len(requirements) + auto_index:03d}"
            sentence = line

        requirements.append(_build_requirement(req_id, sentence))

    return {"requirements": requirements}


def parse_requirements(raw_text: str) -> pd.DataFrame:
    """DataFrame projection of `parse_requirements_struct` for the UI.

    Each row preserves the original sentence and the inferred summary
    columns so the user can edit them via `st.data_editor` before the
    next pipeline stage.
    """
    parsed = parse_requirements_struct(raw_text)
    rows = []
    for req in parsed["requirements"]:
        rows.append({
            "requirement_id": req["requirement_id"],
            "raw_requirement": req["raw_requirement"],
            "input_fields": ", ".join(req.get("inputs", []) or []),
            "data_ranges": req["_summary"]["data_ranges"],
            "conditions": req["_summary"]["conditions"],
            "expected_action": req["_summary"]["expected_action"],
            "target_module": req.get("target_module", "General"),
        })
    return pd.DataFrame(rows)


def _build_requirement(req_id: str, sentence: str) -> Dict[str, Any]:
    """Turn one natural-language sentence into a structured requirement."""
    lower = sentence.lower()
    target_module = _infer_target_module(lower)
    inputs = _infer_inputs(lower)
    constraints = _infer_constraints(lower)
    conditions, data_ranges, expected_action = _infer_summary(lower)

    return {
        "requirement_id": req_id,
        "feature": _infer_feature(sentence),
        "raw_requirement": sentence,
        "target_module": target_module,
        "inputs": inputs,
        "constraints": constraints,
        "conditions": [conditions] if conditions else [],
        "expected_behavior": [expected_action] if expected_action else [],
        # The UI projection uses these compact summaries; not part of the
        # exported schema.
        "_summary": {
            "data_ranges": data_ranges,
            "conditions": conditions,
            "expected_action": expected_action,
        },
    }


def _infer_target_module(lower: str) -> str:
    if any(kw in lower for kw in ("order", "stock", "customer")):
        return "Order Processing"
    if "product" in lower:
        return "Product Management"
    return "General"


def _infer_feature(sentence: str) -> str:
    return sentence[:80]


def _infer_inputs(lower: str) -> List[str]:
    fields: List[str] = []
    if "product" in lower:
        fields.append("product_id")
    if "quantity" in lower or "stock" in lower:
        fields.extend(["quantity", "stock"])
    if "customer" in lower:
        fields.extend(["customer_name", "customer_phone", "customer_address"])
    if "status" in lower:
        fields.append("status")
    if "order" in lower and "items" not in fields:
        fields.append("items")
    # de-dupe preserving order
    seen = set()
    return [f for f in fields if not (f in seen or seen.add(f))]


def _infer_constraints(lower: str) -> List[Dict[str, Any]]:
    """Derive structured constraints from natural-language hints.

    The hints come from the Mini-E-Commerce specification — every
    keyword we look for maps to a constraint type defined in
    `docs/constraint_schema.md`.
    """
    constraints: List[Dict[str, Any]] = []

    if "empty" in lower and ("items" in lower or "order" in lower):
        constraints.append({"field": "items", "type": "numeric_range",
                            "min": 1})

    if "exceeds available stock" in lower or "quantity > stock" in lower:
        constraints.append({"field": "quantity", "type": "relational",
                            "operator": "<=", "target": "stock"})

    if "customer" in lower and (
            "required" in lower or "missing" in lower):
        for field in ("customer_name", "customer_phone", "customer_address"):
            constraints.append({"field": field, "type": "required"})

    if "product" in lower and (
            "create" in lower or "update" in lower or "delete" in lower):
        constraints.append({"field": "product_id", "type": "existence"})

    if "order" in lower and (
            "view" in lower or "detail" in lower):
        constraints.append({"field": "order_id", "type": "existence"})

    if "status" in lower:
        constraints.append({
            "field": "status", "type": "enum",
            "allowed": ["pending", "completed", "cancelled"],
        })

    if not constraints:
        # Generic existence guard so we still emit at least one coverage
        # group for the requirement.
        constraints.append({"field": "request", "type": "existence"})

    return constraints


def _infer_summary(lower: str) -> Tuple[str, str, str]:
    """Return (conditions, data_ranges, expected_action) for the UI table."""
    if "exceeds available stock" in lower:
        return ("insufficient stock", "quantity > stock",
                "reject order and return 400 Bad Request")
    if "empty" in lower:
        return ("empty items array", "items length = 0",
                "reject order and return 400 Bad Request")
    if "missing" in lower:
        return ("missing required customer information",
                "required field is null or empty",
                "reject request and return 400 Bad Request")
    if "reduce" in lower and "stock" in lower:
        return ("successful order",
                "stock after order = original stock − ordered quantity",
                "update product stock")
    if "status" in lower:
        return ("valid order status update",
                "status in [pending, completed, cancelled]",
                "update order status")
    return ("valid request", "valid input range",
            "return successful response")


# ---------------------------------------------------------------------------
# Stage 2 — requirements → risk
# ---------------------------------------------------------------------------

def analyze_risk(requirements_df: pd.DataFrame) -> pd.DataFrame:
    """Score each requirement on four dimensions and map to risk_level.

    Mapping (see `docs/STYLE_GUIDE.md` §4.2):
        risk_score 1-3  → Low
        risk_score 4-7  → Medium
        risk_score 8-10 → High
    """
    rows = []
    for _, row in requirements_df.iterrows():
        text = str(row["raw_requirement"]).lower()
        module = row["target_module"]

        # Each dimension is rated on a 1-3 scale.
        business_impact = 2
        failure_probability = 1
        complexity = 1
        failure_impact = 1

        if "order" in text:
            business_impact = 3
            failure_impact = 3
        if "stock" in text:
            business_impact = 3
            complexity = 2
            failure_impact = 3
        if "reject" in text or "missing" in text or "exceeds" in text:
            failure_probability = 3
        if "status" in text:
            complexity = 2
        if module == "Product Management":
            business_impact = max(business_impact, 2)

        raw_sum = (business_impact + failure_probability
                   + complexity + failure_impact)
        # Linearly squash the raw 4-12 sum into the canonical 1-10 range.
        risk_score = max(1, min(10, round((raw_sum - 4) / 8 * 9 + 1)))

        if risk_score >= 8:
            risk_level = "High"
        elif risk_score >= 4:
            risk_level = "Medium"
        else:
            risk_level = "Low"

        rows.append({
            "requirement_id": row["requirement_id"],
            "target_module": module,
            "business_impact": business_impact,
            "failure_probability": failure_probability,
            "complexity": complexity,
            "failure_impact": failure_impact,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "priority": risk_level,
            "risk_reason": _build_risk_reason(row["raw_requirement"],
                                              risk_level),
        })

    return pd.DataFrame(rows)


def _build_risk_reason(requirement_text: str, priority: str) -> str:
    text = str(requirement_text).lower()
    if "order" in text and "stock" in text:
        return "Order and stock logic directly affects core business correctness."
    if "order" in text:
        return "Order processing is a core business workflow."
    if "reject" in text or "missing" in text:
        return "Invalid input handling drives reliability and UX."
    if "product" in text:
        return "Product data underpins browsing and management."
    return f"Priority classified as {priority} based on impact and complexity."


# ---------------------------------------------------------------------------
# Coverage adapter — forwards to the real engine in core/coverage_analysis
# ---------------------------------------------------------------------------

def coverage_dataframe(coverage_json: Dict[str, Any],
                       risk_df: pd.DataFrame) -> pd.DataFrame:
    """Flatten the coverage JSON for `st.data_editor`."""
    priority_by_req = {
        row["requirement_id"]: row.get("priority", "Medium")
        for _, row in risk_df.iterrows()
    }
    rows = []
    for group in coverage_json.get("coverages", []):
        rid = group.get("requirement_id", "")
        feature = group.get("feature", "")
        for item in group.get("coverage_items", []) or []:
            ctype = (item.get("type") or "positive").lower()
            strategy = _strategy_for_type(ctype)
            rows.append({
                "coverage_item_id": f"CI-{len(rows) + 1:03d}",
                "requirement_id": rid,
                "target_module": feature,
                "coverage_item": item.get("description", ""),
                "coverage_type": ctype,
                "coverage_strategy": strategy,
                "priority": priority_by_req.get(rid, "Medium"),
            })
    return pd.DataFrame(rows)


def _strategy_for_type(ctype: str) -> str:
    if ctype == "boundary":
        return "Boundary Value Analysis"
    if ctype in ("negative", "positive"):
        return "Equivalence Partitioning"
    return "Manual Review"


# ---------------------------------------------------------------------------
# DataFrame ↔ engine JSON adapters
# ---------------------------------------------------------------------------

def coverage_df_to_engine_json(coverage_df: pd.DataFrame,
                               requirements_df: pd.DataFrame
                               ) -> Dict[str, Any]:
    """Convert the editable coverage DataFrame back into the schema the
    black-box engine expects.

    The DataFrame may have been edited by the designer, so we trust its
    `coverage_type` column (already lowercase) and group by requirement.
    """
    groups: List[Dict[str, Any]] = []
    feature_by_req = {
        row["requirement_id"]: row.get("target_module", "")
        for _, row in requirements_df.iterrows()
    }
    for rid in requirements_df["requirement_id"]:
        items = coverage_df[coverage_df["requirement_id"] == rid]
        coverage_items = []
        for _, ci in items.iterrows():
            ctype = str(ci.get("coverage_type", "")).strip().lower()
            if ctype not in {"positive", "negative", "boundary",
                              "combination", "fallback", "unknown"}:
                ctype = _infer_type_from_strategy(
                    str(ci.get("coverage_strategy", "")),
                    str(ci.get("coverage_item", "")))
            coverage_items.append({
                "description": ci.get("coverage_item", ""),
                "type": ctype,
            })
        if coverage_items:
            groups.append({
                "requirement_id": rid,
                "feature": feature_by_req.get(rid, ""),
                "coverage_items": coverage_items,
            })
    return {"coverages": groups}


def _infer_type_from_strategy(strategy: str, text: str) -> str:
    """Heuristic mapping used when the user-edited row omits the type."""
    s = strategy.lower()
    t = text.lower()
    if "boundary" in s or "boundary" in t:
        return "boundary"
    if "decision" in s or "combination" in t:
        # Decision-table inputs are valid positives that exercise the
        # multi-condition combiner; the engine's own DT pass then
        # generates the negative combinations.
        return "positive"
    if any(kw in t for kw in ("reject", "invalid", "missing", "exceeds",
                                "not allowed")):
        return "negative"
    return "positive"


def risk_df_to_engine_json(risk_df: pd.DataFrame) -> Dict[str, Any]:
    """Shape used by both `testcase_generator` and `optimizer`."""
    assessments = []
    for _, row in risk_df.iterrows():
        assessments.append({
            "requirement_id": row["requirement_id"],
            "risk_level": row.get("risk_level", row.get("priority", "Medium")),
            "risk_score": int(row.get("risk_score", 5)),
        })
    return {"risk_assessment": assessments}


def test_cases_json_to_df(test_cases_json: Any) -> pd.DataFrame:
    """Flatten the test_cases list (or optimiser output) for the UI table."""
    if isinstance(test_cases_json, dict):
        cases = (test_cases_json.get("test_cases")
                 or test_cases_json.get("optimized_test_cases") or [])
    else:
        cases = test_cases_json
    return pd.DataFrame(cases)
