"""
AutoTestDesign Streamlit UI (scheduler layer).

This module is intentionally thin: it orchestrates the pipeline modules
under ``core/`` and exposes them as a nine-step Streamlit workflow.

LLM nodes (parser, risk analysis) prefer the live model defined in
``core/parser.py`` / ``core/risk_analysis.py``. When the API key is
missing or the call raises, the UI silently falls back to the
deterministic rule pipeline in ``core/pipeline_fallback.py`` so the
demo always finishes end-to-end.

Pipeline::

    requirement text
        → parse            (LLM or rule)
        → risk analysis    (LLM or rule)
        → coverage items   (rule engine over constraint types)
        → test cases       (EP / BVA / DT engine) + structured oracle
        → state coverage   (white-box state-transition model)
        → optimise         (prioritise + risk-based minimise, optional)
        → export           (CSV / JSON / Excel)
        → run tests        (subprocess pytest against the live backend)

Every editable step uses ``st.data_editor`` so the designer can revise
the artefact and trigger downstream regeneration. This satisfies the
interactive-review requirement of the assignment.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import pandas as pd
import streamlit as st

# Load .env explicitly here so the API key is detected even when the
# optional LLM packages are absent. This must run before _has_llm_key()
# or any os.getenv() lookup below.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from core import (
    coverage_analysis,
    exporter,
    optimizer,
    oracle as oracle_mod,
    pipeline_fallback,
    state_model as state_model_mod,
    test_runner,
    testcase_generator,
)

# LLM modules import OpenAI at import-time; tolerate ImportError so the UI
# works even when openai/python-dotenv are missing.
try:
    from core import parser as llm_parser
    from core import risk_analysis as llm_risk
    _LLM_AVAILABLE = True
except Exception:
    llm_parser = None
    llm_risk = None
    _LLM_AVAILABLE = False


OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


SAMPLE_REQUIREMENTS = """REQ-001: The system shall display all products with name, description, price, and stock.
REQ-002: The system shall allow users to view product details by product ID.
REQ-003: The system shall allow admin users to create a new product with name, description, price, and stock.
REQ-004: The system shall allow admin users to update an existing product.
REQ-005: The system shall allow admin users to delete a product.
REQ-006: The system shall allow users to create an order with one or more products.
REQ-007: The system shall reject an order if the items array is empty.
REQ-008: The system shall reject an order if customer information is missing.
REQ-009: The system shall reject an order if requested quantity exceeds available stock.
REQ-010: The system shall automatically reduce product stock after a successful order.
REQ-011: The system shall allow users to view order details by order ID.
REQ-012: The system shall allow admin users to update order status to pending, completed, or cancelled."""


# ---------------------------------------------------------------------------
# Scheduler helpers
# ---------------------------------------------------------------------------

def _has_llm_key() -> bool:
    """LLM is only attempted when an API key is configured."""
    return bool(os.getenv("API_KEY"))


def _llm_parse_requirements(raw_text: str
                            ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Call the LLM parser and return both the UI DataFrame and the raw
    schema-v1 JSON. The JSON is preserved so the coverage engine — which
    needs the structured ``constraints`` field — can consume it directly.
    """
    if not (_LLM_AVAILABLE and llm_parser):
        raise RuntimeError("LLM parser module unavailable")

    parsed = llm_parser.parse_requirement(raw_text)
    requirements = parsed.get("requirements", []) if isinstance(parsed, dict) \
        else []
    if not requirements:
        raise RuntimeError("LLM parser returned no requirements")

    rows = []
    enriched: List[Dict[str, Any]] = []
    for req in requirements:
        constraints = req.get("constraints", []) or []
        data_ranges = ", ".join(
            _summarise_constraint(c) for c in constraints) or "valid input"
        conditions = ", ".join(req.get("conditions", []) or []) or "valid request"
        expected = ", ".join(req.get("expected_behavior", []) or []) or \
            "return successful response"
        feature = req.get("feature", "")

        if any(k in feature.lower() for k in ("order", "stock", "customer")):
            target_module = "Order Processing"
        elif "product" in feature.lower():
            target_module = "Product Management"
        else:
            target_module = "General"

        rid = req.get("requirement_id") or f"REQ-{len(rows) + 1:03d}"
        raw_sentence = feature or " ".join(req.get("expected_behavior", []))

        rows.append({
            "requirement_id": rid,
            "raw_requirement": raw_sentence,
            "input_fields": ", ".join(req.get("inputs", []) or []),
            "data_ranges": data_ranges,
            "conditions": conditions,
            "expected_action": expected,
            "target_module": target_module,
        })
        # Carry through the structured fields the coverage engine needs.
        enriched.append({
            "requirement_id": rid,
            "feature": feature or raw_sentence,
            "raw_requirement": raw_sentence,
            "target_module": target_module,
            "inputs": req.get("inputs", []) or [],
            "constraints": constraints,
            "conditions": req.get("conditions", []) or [],
            "expected_behavior": req.get("expected_behavior", []) or [],
        })
    return pd.DataFrame(rows), {"requirements": enriched}


def _summarise_constraint(c: Dict[str, Any]) -> str:
    ctype = c.get("type", "")
    field = c.get("field", "")
    if ctype == "length":
        return f"{field} length in [{c.get('min', '?')}, {c.get('max', '?')}]"
    if ctype == "numeric_range":
        return f"{field} in [{c.get('min', '?')}, {c.get('max', '?')}]"
    if ctype == "relational":
        return f"{field} {c.get('operator', '?')} {c.get('target', '?')}"
    if ctype == "enum":
        return f"{field} in {c.get('allowed', [])}"
    return f"{field}:{ctype}"


def _llm_analyse_risk(requirements_df: pd.DataFrame) -> pd.DataFrame:
    """Use the LLM risk analyser per requirement and convert to a DataFrame."""
    if not (_LLM_AVAILABLE and llm_risk):
        raise RuntimeError("LLM risk module unavailable")

    parsed_payload = {
        "requirements": [
            {"requirement_id": row["requirement_id"],
             "feature": row.get("target_module", ""),
             "expected_behavior": [row.get("expected_action", "")]}
            for _, row in requirements_df.iterrows()
        ]
    }
    risk_blob = llm_risk.analyze_risks(parsed_payload)
    assessment = risk_blob.get("risk_assessment", []) if isinstance(
        risk_blob, dict) else []
    if not assessment:
        raise RuntimeError("LLM risk analyser returned no entries")

    by_id = {a["requirement_id"]: a for a in assessment}
    rows = []
    for _, req in requirements_df.iterrows():
        rid = req["requirement_id"]
        entry = by_id.get(rid, {"risk_level": "Medium", "risk_score": 5})
        risk_level = entry.get("risk_level", "Medium")
        rows.append({
            "requirement_id": rid,
            "target_module": req.get("target_module", ""),
            "business_impact": entry.get("business_impact", "-"),
            "failure_probability": entry.get("failure_probability", "-"),
            "complexity": entry.get("complexity", "-"),
            "failure_impact": entry.get("failure_impact", "-"),
            "risk_score": int(entry.get("risk_score", 5)),
            "risk_level": risk_level,
            "priority": risk_level,
            "risk_reason": "; ".join(entry.get("factors", []) or [])
                            or "LLM-derived risk",
        })
    return pd.DataFrame(rows)


def parse_with_fallback(raw_text: str
                        ) -> Tuple[pd.DataFrame, Dict[str, Any], str]:
    """Try the LLM parser, fall back to the rule parser on any error.

    Returns ``(dataframe_for_ui, structured_json, source_label)``.
    The structured JSON is the canonical schema-v1 form used by every
    downstream pipeline stage.
    """
    if _has_llm_key():
        try:
            df, parsed = _llm_parse_requirements(raw_text)
            return df, parsed, "LLM"
        except Exception as exc:  # noqa: BLE001
            st.warning(f"LLM parser failed, using rule fallback. ({exc})")
    df = pipeline_fallback.parse_requirements(raw_text)
    parsed = pipeline_fallback.parse_requirements_struct(raw_text)
    return df, parsed, "Rule"


def analyse_risk_with_fallback(requirements_df: pd.DataFrame
                               ) -> Tuple[pd.DataFrame, str]:
    """Try LLM risk analyser, fall back to rules."""
    if _has_llm_key():
        try:
            df = _llm_analyse_risk(requirements_df)
            return df, "LLM"
        except Exception as exc:  # noqa: BLE001
            st.warning(f"LLM risk analysis failed, using rule fallback. ({exc})")
    return pipeline_fallback.analyze_risk(requirements_df), "Rule"


def generate_coverage(parsed_struct: Dict[str, Any],
                      risk_df: pd.DataFrame) -> pd.DataFrame:
    """Coverage items derive from the structured constraints via the
    deterministic engine in ``core/coverage_analysis.py``.

    Same parsed input → same coverage items, regardless of who produced
    the structured requirements (LLM or rule parser).
    """
    coverage_json = coverage_analysis.generate_coverage(parsed_struct)
    return pipeline_fallback.coverage_dataframe(coverage_json, risk_df)


def generate_test_cases(requirements_df: pd.DataFrame,
                        risk_df: pd.DataFrame,
                        coverage_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Bridge the DataFrames into core/testcase_generator and back."""
    cov_json = pipeline_fallback.coverage_df_to_engine_json(
        coverage_df, requirements_df)
    risk_json = pipeline_fallback.risk_df_to_engine_json(risk_df)
    result = testcase_generator.generate_test_cases(cov_json, risk_json)
    # FR 5.0 — synthesise a structured oracle for every case.
    requirements_payload = [
        {
            "requirement_id": row["requirement_id"],
            "feature": row.get("target_module", ""),
            "expected_behavior": [row.get("expected_action", "")],
        }
        for _, row in requirements_df.iterrows()
    ]
    oracle_mod.attach_oracles(result["test_cases"], requirements_payload)
    df = pipeline_fallback.test_cases_json_to_df(result)
    return df, result.get("summary", {})


def optimise_test_cases(test_cases_df: pd.DataFrame,
                        risk_df: pd.DataFrame,
                        minimize: bool) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run prioritisation (always) + optional risk-based minimisation."""
    cases = test_cases_df.to_dict(orient="records") if isinstance(
        test_cases_df, pd.DataFrame) else test_cases_df
    risk_json = pipeline_fallback.risk_df_to_engine_json(risk_df)
    result = optimizer.optimize_test_suite(
        {"test_cases": cases}, risk_json, minimize=minimize)
    df = pipeline_fallback.test_cases_json_to_df(result)
    return df, result.get("optimization_summary", {})


def export_results(requirements_df: pd.DataFrame,
                   risk_df: pd.DataFrame,
                   coverage_df: pd.DataFrame,
                   test_cases_df: pd.DataFrame) -> Dict[str, str]:
    """Delegate to [core/exporter.py](core/exporter.py)."""
    return exporter.export_all(
        requirements=requirements_df,
        risk=risk_df,
        coverage=coverage_df,
        test_cases=test_cases_df,
        output_dir=OUTPUT_DIR,
    )


# ===========================================================================
# UI layer — a guided, single-direction pipeline.
#
# The workflow is a true pipeline: a step unlocks only once its upstream
# step has produced output. The sidebar is a read-only progress tracker;
# the user advances with explicit "Next" buttons and may step back to
# review or redo an earlier stage. Editing an upstream artefact relocks
# everything downstream so stale results can never leak forward.
#
# Every action gives feedback: long tasks (LLM calls, pytest runs) render
# an st.status block; short tasks toast and show a result banner.
# ===========================================================================


def _invalidate_downstream(*keys: str) -> None:
    """Drop cached downstream artefacts so they are regenerated on demand."""
    for k in keys:
        st.session_state.pop(k, None)


# --- Step registry ---------------------------------------------------------

STEPS: List[Dict[str, str]] = [
    {"key": "input",    "title": "Requirement Input",  "fr": "FR 1.0"},
    {"key": "parse",    "title": "Requirement Structuring", "fr": "FR 1.1"},
    {"key": "risk",     "title": "Risk Analysis",      "fr": "FR 2.0"},
    {"key": "coverage", "title": "Coverage Items",     "fr": "FR 3.0 prep"},
    {"key": "cases",    "title": "Test Cases",         "fr": "FR 3.0 / 4.0 / 5.0"},
    {"key": "optimize", "title": "Optimisation",       "fr": "FR 7.0"},
    {"key": "export",   "title": "Export",             "fr": "FR 6.0"},
    {"key": "run",      "title": "Run Tests",          "fr": "Execution"},
]
N_STEPS = len(STEPS)


# --- Session bootstrap ------------------------------------------------------

def _init_state() -> None:
    defaults = {
        "stage": 0,                       # highest unlocked step index
        "current": 0,                     # step the user is viewing
        "raw_requirements": SAMPLE_REQUIREMENTS,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def _unlock(step_index: int) -> None:
    """Mark a step as completed, unlocking the next one."""
    st.session_state.stage = max(st.session_state.stage, step_index + 1)


def _relock_after(step_index: int, *artefact_keys: str) -> None:
    """An upstream edit invalidates everything downstream.

    Drops the cached artefacts and rolls the unlocked frontier back to
    the edited step so the user must walk forward again.
    """
    _invalidate_downstream(*artefact_keys)
    st.session_state.stage = min(st.session_state.stage, step_index + 1)


def _goto(step_index: int) -> None:
    st.session_state.current = step_index


# --- Sidebar: read-only progress tracker -----------------------------------

def _render_sidebar() -> None:
    st.sidebar.title("AutoTestDesign")
    st.sidebar.caption("AI-driven test design pipeline")

    st.sidebar.divider()
    st.sidebar.subheader("Progress")
    for i, step in enumerate(STEPS):
        if i < st.session_state.stage:
            icon = "✅"
        elif i == st.session_state.current:
            icon = "▶️"
        elif i <= st.session_state.stage:
            icon = "🔓"
        else:
            icon = "🔒"
        marker = "**" if i == st.session_state.current else ""
        st.sidebar.write(
            f"{icon} {marker}{i + 1}. {step['title']}{marker}")

    st.sidebar.divider()
    st.sidebar.subheader("Engine status")
    key_ok = _has_llm_key()
    st.sidebar.write(f"API key: {'✅' if key_ok else '⚠️'}")
    st.sidebar.write(f"LLM SDK: {'✅' if _LLM_AVAILABLE else '⚠️'}")
    if key_ok and _LLM_AVAILABLE:
        st.sidebar.caption("LLM path active.")
    else:
        st.sidebar.caption("Rule fallback active (deterministic).")
    for label, skey in (("Parser", "requirements_source"),
                        ("Risk", "risk_source")):
        if skey in st.session_state:
            st.sidebar.caption(f"{label}: {st.session_state[skey]}")

    st.sidebar.divider()
    st.sidebar.subheader("Target backend")
    st.session_state.backend_url = st.sidebar.text_input(
        "Backend URL",
        value=st.session_state.get(
            "backend_url",
            os.getenv("BACKEND_BASE_URL", test_runner.DEFAULT_BACKEND_URL)),
        label_visibility="collapsed",
    )
    probe = _cached_probe(st.session_state.backend_url)
    if probe["alive"]:
        st.sidebar.success(f"Reachable (HTTP {probe['status_code']})")
    else:
        st.sidebar.warning("Not reachable — needed only for Step 8.")


@st.cache_data(ttl=3, show_spinner=False)
def _cached_probe(url: str) -> Dict[str, Any]:
    return test_runner.probe_backend(url)


# --- Shared navigation footer ----------------------------------------------

def _nav_footer(step_index: int, *, can_advance: bool,
                advance_label: str = "Next step →") -> None:
    """Render Back / Next controls, anchored to the bottom-right."""
    st.divider()
    # The wide first column is an empty spacer that pushes the two
    # buttons to the bottom-right corner.
    _, back_col, next_col = st.columns([6, 1.4, 1.4])
    if step_index > 0:
        if back_col.button("← Back", key=f"back_{step_index}",
                           width="stretch"):
            _goto(step_index - 1)
            st.rerun()
    if step_index < N_STEPS - 1:
        if can_advance:
            if next_col.button(advance_label, key=f"next_{step_index}",
                               type="primary", width="stretch"):
                _unlock(step_index)
                _goto(step_index + 1)
                st.rerun()
        else:
            next_col.button(advance_label, key=f"next_{step_index}",
                            disabled=True, width="stretch",
                            help="Complete this step to continue.")


def _step_header(step_index: int) -> None:
    step = STEPS[step_index]
    st.subheader(f"Step {step_index + 1} / {N_STEPS} — {step['title']}")
    st.caption(step["fr"])


# ===========================================================================
# Step 1 — Requirement Input
# ===========================================================================

def step_input(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Provide the requirements of the **target application** "
        "(Mini-E-Commerce backend). Load the built-in sample or upload a "
        "CSV, then edit the text directly if needed. This text is the input "
        "to the parser.")

    src = st.radio(
        "Requirement source",
        ["Built-in Mini-E-Commerce sample", "Upload a CSV"],
        horizontal=True,
        key="req_source_choice",
    )

    if src == "Built-in Mini-E-Commerce sample":
        if st.button("Load sample requirements"):
            st.session_state.raw_requirements = SAMPLE_REQUIREMENTS
            _relock_after(idx, "requirements_df", "parsed_struct", "risk_df",
                          "coverage_df", "test_cases_df", "test_cases_summary",
                          "optimized_df", "optimization_summary",
                          "test_run_summary")
            st.toast("Sample requirements loaded.")
    else:  # Upload a CSV
        up = st.file_uploader(
            "CSV with a 'raw_requirement' column (optional 'requirement_id')",
            type=["csv"])
        if up is not None:
            df = pd.read_csv(up)
            if "raw_requirement" not in df.columns:
                st.error("CSV must contain a 'raw_requirement' column.")
            else:
                lines = []
                for i, row in df.iterrows():
                    rid = row.get("requirement_id", f"REQ-{i + 1:03d}")
                    lines.append(f"{rid}: {row['raw_requirement']}")
                st.session_state.raw_requirements = "\n".join(lines)
                _relock_after(idx, "requirements_df", "parsed_struct",
                              "risk_df", "coverage_df", "test_cases_df",
                              "test_cases_summary", "optimized_df",
                              "optimization_summary", "test_run_summary")
                st.success(f"Loaded {len(lines)} requirements from CSV.")

    st.session_state.raw_requirements = st.text_area(
        "Requirement text (editable)",
        value=st.session_state.raw_requirements,
        height=280,
        help="Edit directly here regardless of the source chosen above.",
    )

    n_lines = len([ln for ln in st.session_state.raw_requirements.splitlines()
                   if ln.strip()])
    st.caption(f"{n_lines} non-empty requirement line(s) ready.")

    _nav_footer(idx, can_advance=n_lines > 0,
                advance_label="Confirm & continue →")


# ===========================================================================
# Step 2 — Requirement Structuring
# ===========================================================================

def step_parse(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Parse the text into structured requirements. The LLM parser runs "
        "if configured, otherwise a deterministic rule parser is used.")

    if st.button("Parse requirements", type="primary"):
        _relock_after(idx, "requirements_df", "parsed_struct", "risk_df",
                      "coverage_df", "test_cases_df", "test_cases_summary",
                      "optimized_df", "optimization_summary",
                      "test_run_summary")
        with st.status("Parsing requirements…", expanded=True) as status:
            st.write("Sending requirement text to the parser.")
            df, parsed, source = parse_with_fallback(
                st.session_state.raw_requirements)
            st.session_state.requirements_df = df
            st.session_state.parsed_struct = parsed
            st.session_state.requirements_source = source
            st.write(f"Parsed {len(df)} requirements via the {source} path.")
            status.update(label=f"Parsed {len(df)} requirements ({source}).",
                          state="complete")

    if "requirements_df" in st.session_state:
        st.success(
            f"{len(st.session_state.requirements_df)} structured requirements "
            f"(source: {st.session_state.get('requirements_source', '?')}). "
            "Review or edit below.")
        edited = st.data_editor(
            st.session_state.requirements_df,
            width="stretch", num_rows="dynamic", key="req_editor")
        if not edited.equals(st.session_state.requirements_df):
            st.session_state.requirements_df = edited
            _relock_after(idx, "risk_df", "coverage_df", "test_cases_df",
                          "test_cases_summary", "optimized_df",
                          "optimization_summary", "test_run_summary")
            st.toast("Edited — downstream steps will regenerate.")
        _nav_footer(idx, can_advance=True)
    else:
        _nav_footer(idx, can_advance=False)


# ===========================================================================
# Step 3 — Risk Analysis
# ===========================================================================

def step_risk(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Score each requirement (1–10) on four risk dimensions and map it "
        "to a priority. Higher risk earns deeper coverage downstream.")

    if st.button("Generate risk analysis", type="primary"):
        with st.status("Analysing risk…", expanded=True) as status:
            st.write("Scoring requirements.")
            df, source = analyse_risk_with_fallback(
                st.session_state.requirements_df)
            st.session_state.risk_df = df
            st.session_state.risk_source = source
            _relock_after(idx, "coverage_df", "test_cases_df",
                          "test_cases_summary", "optimized_df",
                          "optimization_summary", "test_run_summary")
            status.update(label=f"Risk scored for {len(df)} requirements "
                          f"({source}).", state="complete")

    if "risk_df" in st.session_state:
        rdf = st.session_state.risk_df
        levels = rdf["risk_level"].value_counts().to_dict() \
            if "risk_level" in rdf.columns else {}
        c1, c2, c3 = st.columns(3)
        c1.metric("High", levels.get("High", 0))
        c2.metric("Medium", levels.get("Medium", 0))
        c3.metric("Low", levels.get("Low", 0))
        st.caption("Adjust scores or levels manually if you disagree.")
        edited = st.data_editor(
            rdf, width="stretch", num_rows="dynamic", key="risk_editor")
        if not edited.equals(rdf):
            st.session_state.risk_df = edited
            _relock_after(idx, "coverage_df", "test_cases_df",
                          "test_cases_summary", "optimized_df",
                          "optimization_summary", "test_run_summary")
            st.toast("Edited — downstream steps will regenerate.")
        _nav_footer(idx, can_advance=True)
    else:
        _nav_footer(idx, can_advance=False)


# ===========================================================================
# Step 4 — Coverage Items
# ===========================================================================

def step_coverage(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Expand each requirement's constraints into coverage items "
        "(positive / negative / boundary). This is the key interactive-review "
        "point — edits here reshape the generated test cases.")

    if st.button("Generate coverage items", type="primary"):
        with st.status("Generating coverage items…") as status:
            st.session_state.coverage_df = generate_coverage(
                st.session_state.parsed_struct, st.session_state.risk_df)
            _relock_after(idx, "test_cases_df", "test_cases_summary",
                          "optimized_df", "optimization_summary",
                          "test_run_summary")
            status.update(
                label=f"{len(st.session_state.coverage_df)} coverage items "
                "generated.", state="complete")

    if "coverage_df" in st.session_state:
        st.success(
            f"{len(st.session_state.coverage_df)} coverage items. "
            "Edit, add or remove items below.")
        edited = st.data_editor(
            st.session_state.coverage_df, width="stretch",
            num_rows="dynamic", key="cov_editor")
        if not edited.equals(st.session_state.coverage_df):
            st.session_state.coverage_df = edited
            _relock_after(idx, "test_cases_df", "test_cases_summary",
                          "optimized_df", "optimization_summary",
                          "test_run_summary")
            st.toast("Edited — test cases will regenerate.")
        _nav_footer(idx, can_advance=True)
    else:
        _nav_footer(idx, can_advance=False)


# ===========================================================================
# Step 5 — Test Cases (+ white-box state coverage)
# ===========================================================================

_STATE_STRATEGIES = {
    "All states": "all_states",
    "All valid transitions": "all_transitions",
    "All transitions + invalid guards": "all_transitions+guards",
}


def step_cases(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Generate black-box test cases (EP / BVA / DT) with an attached "
        "oracle, then optionally append white-box state-transition cases.")

    if st.button("Generate test cases", type="primary"):
        with st.status("Generating test cases…") as status:
            df, summary = generate_test_cases(
                st.session_state.requirements_df,
                st.session_state.risk_df,
                st.session_state.coverage_df)
            st.session_state.test_cases_df = df
            st.session_state.test_cases_summary = summary
            _relock_after(idx, "optimized_df", "optimization_summary",
                          "test_run_summary")
            status.update(label=f"{summary.get('total', 0)} test cases "
                          "generated.", state="complete")

    if "test_cases_df" in st.session_state:
        summary = st.session_state.get("test_cases_summary", {})
        tcdf = st.session_state.test_cases_df
        oracled = int(tcdf["oracle"].notna().sum()) \
            if "oracle" in tcdf.columns else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", summary.get("total", 0))
        c2.metric("Techniques", len(summary.get("by_technique", {})))
        c3.metric("Priorities", len(summary.get("by_priority", {})))
        c4.metric("With oracle", oracled)
        with st.expander("Summary detail"):
            st.json(summary)

        edited = st.data_editor(
            tcdf, width="stretch", num_rows="dynamic", key="tc_editor")
        if not edited.equals(tcdf):
            st.session_state.test_cases_df = edited
            _relock_after(idx, "optimized_df", "optimization_summary",
                          "test_run_summary")
            st.toast("Edited — optimisation result cleared.")

        st.divider()
        st.markdown("**White-box state-transition coverage (FR 4.0)**")
        st.caption(
            "Append cases derived from the order status state machine "
            "(`pending → completed / cancelled`). Select a coverage "
            "criterion and click *Generate & append* to add new cases "
            "to the test-case table above.")
        cs = st.columns([2, 1])
        label = cs[0].selectbox(
            "Coverage criterion", list(_STATE_STRATEGIES.keys()), index=2)
        if cs[1].button("Generate & append"):
            with st.status("Generating state-coverage cases…") as status:
                model = state_model_mod.load_default_order_model()
                res = state_model_mod.generate_state_test_cases(
                    model, strategy=_STATE_STRATEGIES[label])
                sdf = pd.DataFrame(res["test_cases"])
                # Replace any previously appended state-transition cases for
                # this model rather than skipping on a test_case_id clash:
                # different criteria reuse the same S-prefixed ids, so a plain
                # "already present" filter would silently no-op when switching
                # criterion. Drop the old ST cases, then append the new set.
                current = st.session_state.test_cases_df
                kept = current[
                    current.get("test_design_technique",
                                pd.Series(dtype=str))
                    != state_model_mod.TECHNIQUE]
                st.session_state.test_cases_df = pd.concat(
                    [kept, sdf], ignore_index=True)
                _relock_after(idx, "optimized_df", "optimization_summary",
                              "test_run_summary")
                status.update(
                    label=f"Set {len(sdf)} state-coverage cases "
                          f"(«{label}»).", state="complete")
            st.rerun()

        with st.expander(f"Edges covered by «{label}»"):
            model = state_model_mod.load_default_order_model()
            strategy = _STATE_STRATEGIES[label]
            # Show exactly the edges that the selected criterion exercises:
            #   all_states / all_transitions  -> the valid edges only
            #   all_transitions+guards        -> valid edges plus the
            #                                    declared invalid guards
            if strategy == "all_transitions+guards":
                edges = list(model.transitions)
            else:
                edges = [t for t in model.transitions if t.valid]
            st.write(f"Initial: `{model.initial}` · "
                     f"States: {', '.join(model.states)} · "
                     f"Terminal: {', '.join(model.terminal)}")
            st.dataframe(pd.DataFrame([
                {"source": t.source, "event": t.event, "target": t.target,
                 "valid": "✅" if t.valid else "❌"}
                for t in edges
            ]), width="stretch", hide_index=True)

        _nav_footer(idx, can_advance=True)
    else:
        _nav_footer(idx, can_advance=False)


# ===========================================================================
# Step 6 — Optimisation
# ===========================================================================

def step_optimize(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Prioritise the suite by risk and technique, and optionally minimise "
        "it — removing redundancy while keeping every requirement covered.")

    cols = st.columns(2)
    if cols[0].button("Prioritise", type="primary"):
        with st.status("Prioritising…") as status:
            df, summary = optimise_test_cases(
                st.session_state.test_cases_df, st.session_state.risk_df,
                minimize=False)
            st.session_state.optimized_df = df
            st.session_state.optimization_summary = summary
            st.session_state.pop("test_run_summary", None)
            status.update(label="Prioritised.", state="complete")
    if cols[1].button("Minimise (risk-based)"):
        with st.status("Minimising…") as status:
            df, summary = optimise_test_cases(
                st.session_state.test_cases_df, st.session_state.risk_df,
                minimize=True)
            st.session_state.optimized_df = df
            st.session_state.optimization_summary = summary
            st.session_state.pop("test_run_summary", None)
            status.update(label="Minimised.", state="complete")

    summary = st.session_state.get("optimization_summary")
    if summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Original", summary.get("original_count", 0))
        c2.metric("Optimised", summary.get("optimized_count", 0))
        c3.metric("Removed", summary.get("removed_count", 0))
        c4.metric("Strategy", summary.get("strategy", "-"))

        before = st.session_state.test_cases_df
        after = st.session_state.optimized_df
        if "test_design_technique" in before.columns:
            chart = pd.DataFrame({
                "Original": before["test_design_technique"].value_counts(),
                "Optimised": after["test_design_technique"].value_counts(),
            }).fillna(0)
            st.bar_chart(chart)
        st.dataframe(after, width="stretch")

    # Optimisation is optional — the user can always advance.
    _nav_footer(idx, can_advance=True)


# ===========================================================================
# Step 7 — Export
# ===========================================================================

def step_export(idx: int) -> None:
    _step_header(idx)
    st.write("Export the suite to CSV, JSON and a multi-sheet Excel workbook.")

    use_opt = False
    if st.session_state.get("optimized_df") is not None:
        use_opt = st.checkbox("Export the optimised set", value=True)

    if st.button("Export CSV / JSON / Excel", type="primary"):
        with st.status("Writing artefacts…") as status:
            cases = (st.session_state.optimized_df if use_opt
                     else st.session_state.test_cases_df)
            paths = export_results(
                st.session_state.requirements_df, st.session_state.risk_df,
                st.session_state.coverage_df, cases)
            st.session_state.export_paths = paths
            status.update(label="Export complete.", state="complete")

    if "export_paths" in st.session_state:
        st.success("Artefacts written to outputs/.")
        for name, path in st.session_state.export_paths.items():
            st.write(f"- **{name}**: `{path}`")
        _nav_footer(idx, can_advance=True)
    else:
        _nav_footer(idx, can_advance=False)


# ===========================================================================
# Step 8 — Run Tests
# ===========================================================================

def _event_sequence_fingerprint(tc: Dict[str, Any]) -> str:
    """Event-sequence signature of a state-transition case (empty for
    black-box cases). Mirrors the harness dedup so the UI count matches
    the number of HTTP checks actually executed."""
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


def _count_executable(cases: List[Dict[str, Any]]) -> int:
    """Number of HTTP checks the harness will run: one representative per
    unique (requirement_id, coverage_type, event_sequence) key (matches
    the dedup the data-driven harness applies before execution)."""
    seen = set()
    for c in cases:
        seen.add((str(c.get("requirement_id", "")),
                  str(c.get("coverage_type", "")).lower(),
                  _event_sequence_fingerprint(c)))
    return len(seen)


def step_run(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Execute the test cases against the live backend through pytest and "
        "view a per-case pass / fail report.")

    source = st.radio(
        "Test cases source",
        ["Generated (current session)", "Optimised (current session)",
         "Baseline (data/baseline)"],
        index=0, horizontal=True)

    if source == "Optimised (current session)":
        cases = (st.session_state.optimized_df.to_dict(orient="records")
                 if st.session_state.get("optimized_df") is not None else [])
        if not cases:
            st.info("No optimised set yet — run Step 6 or pick another source.")
    elif source == "Baseline (data/baseline)":
        try:
            with open("data/baseline/test_cases.json", encoding="utf-8") as f:
                cases = json.load(f).get("test_cases", [])
        except FileNotFoundError:
            st.error("Baseline file not found.")
            cases = []
    else:
        cases = st.session_state.test_cases_df.to_dict(orient="records")

    probe = _cached_probe(st.session_state.backend_url)
    if not probe["alive"]:
        st.warning(
            "Backend not reachable. Start it and refresh — see the sidebar.")

    if cases:
        executable = _count_executable(cases)
        st.caption(
            f"{len(cases)} generated · {executable} will execute → "
            f"{st.session_state.backend_url}")
        if executable < len(cases):
            st.info(
                f"ℹ️ {len(cases)} cases collapse to {executable} HTTP "
                "checks. The harness runs **one representative per "
                "(requirement × coverage type)**: many generated cases "
                "share the same requirement and type (e.g. five separate "
                "'valid field' positives for one create-product request), "
                "so executing each once avoids identical, redundant "
                "requests. Every case still appears in the export and the "
                "traceability matrix — only the live HTTP execution is "
                "deduplicated.")
    if st.button("▶ Run data-driven tests", type="primary",
                 disabled=not cases or not probe["alive"]):
        with st.status("Running pytest against the backend…",
                       expanded=True) as status:
            st.write("Spawning pytest subprocess.")
            summary = test_runner.run_data_driven_tests(
                test_cases=cases, backend_url=st.session_state.backend_url)
            st.session_state.test_run_summary = summary
            status.update(
                label=f"Done — {summary.passed} passed, {summary.failed} "
                f"failed, {summary.skipped} skipped.",
                state="complete" if summary.is_clean() else "error")

    summary = st.session_state.get("test_run_summary")
    if summary:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total", summary.total)
        c2.metric("Passed", summary.passed)
        c3.metric("Failed", summary.failed)
        c4.metric("Skipped", summary.skipped)
        c5.metric("Seconds", round(summary.duration_seconds, 2))
        if summary.is_clean() and summary.total:
            st.success("All executed cases passed against the backend.")
        elif summary.failed:
            st.warning(f"{summary.failed} case(s) failed — see below.")
        if summary.results:
            st.dataframe(pd.DataFrame([r.as_row() for r in summary.results]),
                         width="stretch", hide_index=True)
            for r in summary.results:
                if r.outcome in ("failed", "error"):
                    with st.expander(f"❌ {r.test_case_id} — {r.coverage_type}"):
                        st.code(r.message or "(no message)")
        with st.expander("Raw pytest output"):
            st.code(summary.raw_output or "(empty)")

    _nav_footer(idx, can_advance=False)
    st.divider()
    if st.button("↺ Start a new run (reset pipeline)"):
        for k in list(st.session_state.keys()):
            if k not in ("backend_url",):
                del st.session_state[k]
        st.rerun()


# ===========================================================================
# Router
# ===========================================================================

_RENDERERS = [step_input, step_parse, step_risk, step_coverage,
              step_cases, step_optimize, step_export, step_run]


def main() -> None:
    _init_state()
    _render_sidebar()

    st.title("AI-driven AutoTestDesign Tool")
    st.caption(
        "Requirements → Risk → Coverage → Test Cases → Optimise → Export → Run")
    st.divider()

    # Navigation is strictly Back / Next; there is no step picker. Clamp
    # the current step in case an upstream edit rolled the frontier back.
    if st.session_state.current > st.session_state.stage:
        st.session_state.current = st.session_state.stage

    _RENDERERS[st.session_state.current](st.session_state.current)


st.set_page_config(page_title="AutoTestDesign", layout="wide")
main()
