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
import time
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
    report_generator,
    report_pipeline,
    run_context,
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


# Stable display/aggregation order for the design-phase pipeline stages.
_TIMING_ORDER = ["parse", "risk", "coverage", "testcases", "optimize"]


def _record_timing(stage: str, engine: str, seconds: float) -> None:
    """Record the wall-clock duration of one design step. Keyed by stage
    so re-running a step overwrites rather than accumulates."""
    st.session_state.setdefault("timings", {})[stage] = {
        "stage": stage, "engine": engine, "seconds": round(seconds, 4)}


def _ordered_timings() -> List[Dict[str, Any]]:
    """The recorded timings in pipeline order, for the cost section."""
    timings = st.session_state.get("timings", {})
    ordered = [timings[s] for s in _TIMING_ORDER if s in timings]
    # Append any stages not in the canonical order (future-proofing).
    ordered += [v for k, v in timings.items() if k not in _TIMING_ORDER]
    return ordered


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
    """Delegate to [core/exporter.py](core/exporter.py).

    Data artefacts are written into the current run's ``data/``
    sub-directory so every output of a session lives under one
    ``outputs/run_<ts>/`` tree (see [core/run_context.py](core/run_context.py)).
    """
    dirs = run_context.ensure_run_dirs(st.session_state.run_id)
    return exporter.export_all(
        requirements=requirements_df,
        risk=risk_df,
        coverage=coverage_df,
        test_cases=test_cases_df,
        output_dir=dirs["data"],
    )


def _engine_source_label() -> str:
    """Human-readable description of which design engine produced the run."""
    parts = []
    if st.session_state.get("requirements_source"):
        parts.append(f"parser={st.session_state['requirements_source']}")
    if st.session_state.get("risk_source"):
        parts.append(f"risk={st.session_state['risk_source']}")
    return ", ".join(parts) or "rule pipeline"


def _canonical_run(runs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the run whose results anchor the detailed report's per-case
    table and §4 design set: prefer the optimised + deduplicated run (the
    suite the team ships), then fall back to the most recent run."""
    for key in ("Optimised|dedup", "Optimised|full", "Generated|dedup"):
        if key in runs:
            return runs[key]
    last = st.session_state.get("last_run_key")
    if last in runs:
        return runs[last]
    return next(iter(runs.values())) if runs else {}


def generate_run_reports() -> Dict[str, Any]:
    """Render the three Markdown deliverables into the run's ``docs/``
    directory from the artefacts the session currently holds.

    Delegates to the orchestrator in
    [core/report_pipeline.py](core/report_pipeline.py): each document is
    written by the LLM when configured, else by the deterministic rule
    generator, and the measured generation time + token usage are injected
    into the cost section. Every recorded Step 8 run mode feeds the
    detailed report's per-mode comparison table; the canonical run (see
    :func:`_canonical_run`) supplies the per-case result detail and the
    design set shown in the report tables, keeping the design and result
    sections on the same source.

    Returns the orchestrator's result dict: ``{"paths", "metrics",
    "engine_by_doc"}``.
    """
    dirs = run_context.ensure_run_dirs(st.session_state.run_id)
    meta = {
        "run_id": st.session_state.run_id,
        "target_app": report_generator.DEFAULT_TARGET_APP,
        "engine_source": _engine_source_label(),
    }

    runs = st.session_state.get("runs_by_mode") or {}
    canonical = _canonical_run(runs)
    # Design tables follow the canonical run's source set when a run
    # exists, else the optimised (or generated) design set.
    if canonical.get("cases") is not None:
        design_cases: Any = canonical["cases"]
    elif st.session_state.get("optimized_df") is not None:
        design_cases = st.session_state.get("optimized_df")
    else:
        design_cases = st.session_state.get("test_cases_df")

    return report_pipeline.generate_reports(
        requirements=st.session_state.get("requirements_df"),
        risk=st.session_state.get("risk_df"),
        coverage=st.session_state.get("coverage_df"),
        test_cases=design_cases,
        docs_dir=dirs["docs"],
        test_summary=st.session_state.get("test_cases_summary"),
        optimization_summary=st.session_state.get("optimization_summary"),
        run_summary=canonical.get("summary"),
        runs=list(runs.values()),
        pipeline_timings=_ordered_timings(),
        meta=meta,
        prefer_llm=_has_llm_key(),
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
    # The per-mode run records are coupled to the test-run summary: any
    # relock that clears the summary must also clear the recorded modes,
    # so an upstream edit never leaves a stale run table behind.
    if "test_run_summary" in keys:
        st.session_state.pop("runs_by_mode", None)
        st.session_state.pop("last_run_key", None)


# --- Step registry ---------------------------------------------------------

STEPS: List[Dict[str, str]] = [
    {"key": "landing",  "title": "Welcome",            "fr": "Choose a path"},
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
        # One run id per session, fixed when the landing page is first
        # reached. All exports and generated docs of this session live
        # under outputs/run_<ts>/ (see core/run_context.py).
        "run_id": run_context.new_run_id(),
        # stage -> {stage, engine, seconds}: wall-clock timing of each
        # design step, fed into the cost estimation of the reports.
        "timings": {},
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
        # Landing page is rendered without a step number; pipeline steps
        # are numbered 1..N-1.
        label = step["title"] if i == 0 else f"{i}. {step['title']}"
        st.sidebar.write(f"{icon} {marker}{label}{marker}")

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
    """Render Back / Next (or Restart on the last step) controls,
    anchored to the bottom-right."""
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
    else:
        # Last step: the Next slot becomes a "Restart" control so the
        # user can begin a fresh run from the same bottom-right corner
        # they have been using throughout the pipeline.
        if next_col.button("↺ Restart", key=f"restart_{step_index}",
                           type="primary", width="stretch",
                           help="Reset the pipeline and start a new run."):
            for k in list(st.session_state.keys()):
                if k not in ("backend_url",):
                    del st.session_state[k]
            st.rerun()


def _step_header(step_index: int) -> None:
    step = STEPS[step_index]
    # Landing page renders without a step number; pipeline steps are
    # numbered 1..N-1 (the landing page does not consume a number).
    if step_index == 0:
        st.subheader(step["title"])
    else:
        st.subheader(
            f"Step {step_index} / {N_STEPS - 1} — {step['title']}")
    st.caption(step["fr"])


# ===========================================================================
# Step 0 — Landing page
# ===========================================================================

def step_landing(idx: int) -> None:
    """Entry page. The visitor either executes the persisted baseline
    here, or advances into the full design pipeline."""
    _step_header(idx)
    st.write(
        "Welcome to **AutoTestDesign**. Execute the persisted baseline "
        "against the live backend on this page, or press *Next step* to "
        "start the full design pipeline from requirement input.")

    baseline_choice = st.radio(
        "Baseline source",
        ["Baseline — raw (65 cases)",
         "Baseline — optimised (61 cases)"],
        index=0, horizontal=True, key="_landing_baseline_choice")
    kind = "optimised" if "optimised" in baseline_choice else "raw"
    cases = _load_baseline(kind)

    _render_run_panel(cases, run_button_key="_landing_run",
                      summary_session_key="landing_run_summary",
                      mode_key_prefix="landing")

    # Standard footer; the Next button starts the pipeline.
    _nav_footer(idx, can_advance=True,
                advance_label="Start the full pipeline →")


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

    _nav_footer(idx, can_advance=n_lines > 0)


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
            _t0 = time.perf_counter()
            df, parsed, source = parse_with_fallback(
                st.session_state.raw_requirements)
            _record_timing("parse", source, time.perf_counter() - _t0)
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
            # Drop the editor's persisted widget state so the next render
            # re-binds the editor to the now-merged source DataFrame.
            # Without this reset, an "added" row remains in the editor's
            # internal added_rows queue and re-appears as a blank row on
            # the next rerun while the typed values move into the source.
            st.session_state.pop("req_editor", None)
            st.toast("Edited — downstream steps will regenerate.")
            st.rerun()
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
            _t0 = time.perf_counter()
            df, source = analyse_risk_with_fallback(
                st.session_state.requirements_df)
            _record_timing("risk", source, time.perf_counter() - _t0)
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
            st.session_state.pop("risk_editor", None)
            st.toast("Edited — downstream steps will regenerate.")
            st.rerun()
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
            _t0 = time.perf_counter()
            st.session_state.coverage_df = generate_coverage(
                st.session_state.parsed_struct, st.session_state.risk_df)
            _record_timing("coverage", "rule", time.perf_counter() - _t0)
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
            st.session_state.pop("cov_editor", None)
            st.toast("Edited — test cases will regenerate.")
            st.rerun()
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
            _t0 = time.perf_counter()
            df, summary = generate_test_cases(
                st.session_state.requirements_df,
                st.session_state.risk_df,
                st.session_state.coverage_df)
            _record_timing("testcases", "rule", time.perf_counter() - _t0)
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
            # Recompute the summary so Total / Techniques / Priorities
            # follow the editor (rows added or removed by hand).
            by_tech: Dict[str, int] = {}
            by_pri: Dict[str, int] = {}
            if "test_design_technique" in edited.columns:
                for t, n in (edited["test_design_technique"]
                             .value_counts().items()):
                    by_tech[str(t)] = int(n)
            if "priority" in edited.columns:
                for p, n in edited["priority"].value_counts().items():
                    by_pri[str(p)] = int(n)
            st.session_state.test_cases_summary = {
                "total": int(len(edited)),
                "by_technique": by_tech,
                "by_priority": by_pri,
            }
            _relock_after(idx, "optimized_df", "optimization_summary",
                          "test_run_summary")
            st.session_state.pop("tc_editor", None)
            st.toast("Edited — optimisation result cleared.")
            st.rerun()

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
                # Attach a structured oracle to every ST case (FR 5.0),
                # using the originating requirement so any `must_contain`
                # keywords match the black-box path.
                requirements_payload = [
                    {
                        "requirement_id": row["requirement_id"],
                        "feature": row.get("target_module", ""),
                        "expected_behavior": [row.get("expected_action", "")],
                    }
                    for _, row in st.session_state.requirements_df.iterrows()
                ]
                oracle_mod.attach_oracles(
                    res["test_cases"], requirements_payload)
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
                combined = pd.concat([kept, sdf], ignore_index=True)
                st.session_state.test_cases_df = combined
                # Refresh the summary so the metrics row (Total /
                # Techniques / Priorities) reflects the appended ST cases
                # rather than the stale black-box-only counts.
                by_tech: Dict[str, int] = {}
                by_pri: Dict[str, int] = {}
                if "test_design_technique" in combined.columns:
                    for t, n in (combined["test_design_technique"]
                                 .value_counts().items()):
                        by_tech[str(t)] = int(n)
                if "priority" in combined.columns:
                    for p, n in (combined["priority"]
                                 .value_counts().items()):
                        by_pri[str(p)] = int(n)
                st.session_state.test_cases_summary = {
                    "total": int(len(combined)),
                    "by_technique": by_tech,
                    "by_priority": by_pri,
                }
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
    st.caption(
        "**Pick one button** (not both). *Prioritise* only reorders the suite "
        "(High risk first, DT/ST > BVA > EP); the case count does not change. "
        "*Minimise (risk-based)* additionally drops redundant Low/Medium "
        "cases while keeping every requirement covered and every DT and ST "
        "case intact. Both are **manual** — Step 6 stays empty until you "
        "click. *Minimise* is the recommended demo because it exercises the "
        "full FR 7.0.")

    cols = st.columns(2)
    if cols[0].button("Prioritise"):
        with st.status("Prioritising…") as status:
            _t0 = time.perf_counter()
            df, summary = optimise_test_cases(
                st.session_state.test_cases_df, st.session_state.risk_df,
                minimize=False)
            _record_timing("optimize", "rule", time.perf_counter() - _t0)
            st.session_state.optimized_df = df
            st.session_state.optimization_summary = summary
            _invalidate_downstream("test_run_summary")
            status.update(label="Prioritised.", state="complete")
    if cols[1].button("Minimise (risk-based) — Recommended", type="primary"):
        with st.status("Minimising…") as status:
            _t0 = time.perf_counter()
            df, summary = optimise_test_cases(
                st.session_state.test_cases_df, st.session_state.risk_df,
                minimize=True)
            _record_timing("optimize", "rule", time.perf_counter() - _t0)
            st.session_state.optimized_df = df
            st.session_state.optimization_summary = summary
            _invalidate_downstream("test_run_summary")
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
            # Grouped (side-by-side) bars per technique — st.bar_chart with
            # two columns renders them stacked, which is misleading for a
            # before/after comparison. Use Altair with xOffset to place the
            # Original and Optimised bars next to each other.
            try:
                import altair as alt
                bf = before["test_design_technique"].value_counts()
                af = after["test_design_technique"].value_counts()
                chart_df = (
                    pd.DataFrame({"Original": bf, "Optimised": af})
                    .fillna(0).astype(int)
                    .rename_axis("technique").reset_index()
                    .melt("technique", var_name="phase", value_name="count"))
                phase_order = ["Original", "Optimised"]
                grouped = (
                    alt.Chart(chart_df)
                    .mark_bar()
                    .encode(
                        x=alt.X("technique:N", title="Technique"),
                        xOffset=alt.XOffset("phase:N", sort=phase_order),
                        y=alt.Y("count:Q", title="Cases"),
                        color=alt.Color(
                            "phase:N", title="",
                            sort=phase_order,
                            scale=alt.Scale(domain=phase_order)),
                        tooltip=["technique", "phase", "count"]))
                st.altair_chart(grouped, width="stretch")
            except Exception:
                # Defensive fallback: keep the page usable if altair is
                # missing for any reason.
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
    st.write(
        "Export the designed suite to CSV, JSON and a multi-sheet Excel "
        "workbook. These are the design-layer artefacts; the three Markdown "
        "deliverables embed execution results and are generated at Step 8 "
        "after the suite has been run.")
    st.caption(
        f"This session writes everything under "
        f"`{run_context.run_dir(st.session_state.run_id)}/` — data artefacts "
        "in `data/`, deliverable documents in `docs/` (generated at Step 8).")

    use_opt = False
    if st.session_state.get("optimized_df") is not None:
        use_opt = st.checkbox("Export the optimised set", value=True)

    if st.button("Export data artefacts", type="primary"):
        with st.status("Writing artefacts…", expanded=True) as status:
            cases = (st.session_state.optimized_df if use_opt
                     else st.session_state.test_cases_df)
            st.write("Writing CSV / JSON / Excel into data/.")
            paths = export_results(
                st.session_state.requirements_df, st.session_state.risk_df,
                st.session_state.coverage_df, cases)
            st.session_state.export_paths = paths
            status.update(label="Export complete.", state="complete")

    if "export_paths" in st.session_state:
        st.success(
            f"Data artefacts written to "
            f"`{run_context.data_dir(st.session_state.run_id)}/`.")
        for name, path in st.session_state.export_paths.items():
            st.write(f"- **{name}**: `{path}`")
        st.info(
            "Next: run the suite at Step 8, then generate the deliverable "
            "documents there.")
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


def _load_baseline(kind: str) -> List[Dict[str, Any]]:
    """Load one of the two persisted baselines from ``data/baseline/``."""
    if kind == "optimised":
        path = "data/baseline/test_cases_optimized.json"
        key = "optimized_test_cases"
    else:
        path = "data/baseline/test_cases.json"
        key = "test_cases"
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload.get(key) or payload.get("test_cases", [])
    except FileNotFoundError:
        st.error(f"Baseline file not found: {path}")
        return []


def _render_run_panel(cases: List[Dict[str, Any]],
                      *, run_button_key: str,
                      summary_session_key: str = "test_run_summary",
                      mode_key_prefix: str = "run",
                      record_source: str = None) -> None:
    """Shared run-panel: backend probe, executable caption, run button,
    and the post-run summary + per-case table. Reused by Step 0 (baseline
    view) and Step 8 (current-session view).

    When ``record_source`` is given (Step 8 only), each completed run is
    filed in ``st.session_state.runs_by_mode`` under its
    ``(source, http_mode)`` key so the report generator can build the
    multi-mode comparison table. Step 0 baseline runs pass ``None`` and
    are not recorded — they are a demo against persisted data, not part
    of the current session's deliverables."""
    probe = _cached_probe(st.session_state.backend_url)
    if not probe["alive"]:
        st.warning(
            "Backend not reachable. Start it and refresh — see the sidebar.")

    # Execution-mode toggle: by default, the harness collapses cases that
    # share the same HTTP-template key (one representative per
    # requirement × coverage type × event sequence). Enabling this option
    # disables the collapse and executes every case as a separate HTTP
    # request — primarily a diagnostic mode showing the two paths agree.
    full_http_exec = st.checkbox(
        "Run every case individually (no HTTP dedup) — diagnostic mode",
        value=False, key=f"{mode_key_prefix}_full_exec",
        help=("Default: representative-per-key execution. When enabled, "
              "every case is executed as its own HTTP request; this is "
              "slower but proves the deduplicated execution covers the "
              "same observable behaviour."))

    if cases:
        executable = (len(cases) if full_http_exec
                      else _count_executable(cases))
        st.caption(
            f"{len(cases)} generated · {executable} will execute → "
            f"{st.session_state.backend_url}")
        if full_http_exec:
            st.info(
                f"ℹ️ Diagnostic mode is on — all {len(cases)} cases will "
                "be executed individually, with no representative-per-key "
                "collapse.")
        elif executable < len(cases):
            st.info(
                f"ℹ️ {len(cases)} cases collapse to {executable} HTTP "
                "checks. The harness runs **one representative per "
                "(requirement × coverage type × event sequence)**: many "
                "generated cases share the same HTTP-template key (e.g. "
                "five 'valid field' positives for one create-product "
                "request), so executing each once avoids identical, "
                "redundant requests. Every case still appears in the "
                "export and the traceability matrix — only the live HTTP "
                "execution is deduplicated.")
    if st.button("▶ Run data-driven tests", type="primary",
                 key=run_button_key,
                 disabled=not cases or not probe["alive"]):
        with st.status("Running pytest against the backend…",
                       expanded=True) as status:
            st.write("Spawning pytest subprocess.")
            summary = test_runner.run_data_driven_tests(
                test_cases=cases, backend_url=st.session_state.backend_url,
                full_http_exec=full_http_exec,
                output_dir=run_context.runs_dir(st.session_state.run_id))
            st.session_state[summary_session_key] = summary
            if record_source is not None:
                http_mode = "full" if full_http_exec else "dedup"
                runs = st.session_state.setdefault("runs_by_mode", {})
                key = f"{record_source}|{http_mode}"
                runs[key] = {
                    "source": record_source,
                    "http_mode": http_mode,
                    "generated_count": len(cases),
                    "executed_count": (len(cases) if full_http_exec
                                       else _count_executable(cases)),
                    "cases": cases,
                    "summary": summary,
                }
                st.session_state.last_run_key = key
            status.update(
                label=f"Done — {summary.passed} passed, {summary.failed} "
                f"failed, {summary.skipped} skipped.",
                state="complete" if summary.is_clean() else "error")

    summary = st.session_state.get(summary_session_key)
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
                    with st.expander(
                            f"❌ {r.test_case_id} — {r.coverage_type}"):
                        st.code(r.message or "(no message)")
        with st.expander("Raw pytest output"):
            st.code(summary.raw_output or "(empty)")


def step_run(idx: int) -> None:
    _step_header(idx)
    st.write(
        "Execute the test cases against the live backend through pytest and "
        "view a per-case pass / fail report. To execute the persisted "
        "baseline instead, use the Welcome page (Step 0).")

    source = st.radio(
        "Test cases source",
        ["Generated (current session)", "Optimised (current session)"],
        index=0, horizontal=True, key="_run_source")

    if source == "Optimised (current session)":
        cases = (st.session_state.optimized_df.to_dict(orient="records")
                 if st.session_state.get("optimized_df") is not None else [])
        if not cases:
            st.info(
                "No optimised set yet — run Step 6 or switch back to "
                "*Generated (current session)*.")
    else:
        cases = (st.session_state.test_cases_df.to_dict(orient="records")
                 if st.session_state.get("test_cases_df") is not None else [])
        if not cases:
            st.info(
                "No generated set in this session — start the pipeline "
                "from Step 1, or use Step 0 (Welcome) to execute the "
                "persisted baseline.")

    source_label = ("Optimised" if source.startswith("Optimised")
                    else "Generated")
    _render_run_panel(cases, run_button_key="_run_session",
                      summary_session_key="test_run_summary",
                      mode_key_prefix="run", record_source=source_label)

    # Deliverable generation lives here, after execution, because the
    # detailed report's result analysis (and the test plan's execution
    # checklist) need run results. The button is gated on at least one
    # recorded run so the documents are only produced once the data they
    # embed actually exists.
    st.divider()
    st.subheader("Generate deliverable documents")
    runs = st.session_state.get("runs_by_mode") or {}
    engine = "LLM (with rule fallback)" if _has_llm_key() else "rule engine"
    if runs:
        modes = ", ".join(
            f"{r['source']}/{r['http_mode']}" for r in runs.values())
        st.caption(
            f"Run modes recorded this session: **{modes}**. Documents are "
            f"written by the **{engine}** into "
            f"`{run_context.docs_dir(st.session_state.run_id)}` following "
            "IEEE 829, with a per-mode comparison table in the detailed "
            "report and tool-measured generation time + token cost injected "
            "into the test plan.")
    else:
        st.caption(
            "Run the suite at least once above (in any source / HTTP mode) "
            "to unlock document generation — the reports embed the "
            "execution results.")

    if st.button("📄 Generate deliverable documents", type="primary",
                 disabled=not runs,
                 help=None if runs else "Run the suite at least once first."):
        with st.status("Generating documents…", expanded=True) as status:
            st.write(f"Generating via the {engine}.")
            st.session_state.report_result = generate_run_reports()
            status.update(label="Documents written to docs/.",
                          state="complete")

    result = st.session_state.get("report_result")
    if result:
        st.success("Deliverable documents generated.")
        for kind, path in result["paths"].items():
            eng = result["engine_by_doc"].get(kind, "?")
            m = result["metrics"].get(kind, {})
            detail = (f"{eng}, {m.get('seconds', 0):.2f}s"
                      + (f", {m.get('total_tokens', 0)} tok"
                         if m.get("total_tokens") else ""))
            st.write(f"- **{kind}** ({detail}): `{path}`")
        if any(m.get("total_tokens") for m in result["metrics"].values()):
            tot = sum(m.get("total_tokens", 0)
                      for m in result["metrics"].values())
            st.caption(
                f"Total generation tokens: {tot}. Per-document timing and "
                "token cost are embedded in the test plan's cost section.")

    _nav_footer(idx, can_advance=False)


# ===========================================================================
# Router
# ===========================================================================

_RENDERERS = [step_landing, step_input, step_parse, step_risk, step_coverage,
              step_cases, step_optimize, step_export, step_run]


def main() -> None:
    _init_state()
    _render_sidebar()

    st.title("AI-driven AutoTestDesign Tool")
    st.caption(
        "Requirements → Risk → Coverage → Test Cases → Optimise → Export → Run")
    st.divider()

    if st.session_state.current > st.session_state.stage:
        st.session_state.current = st.session_state.stage

    _RENDERERS[st.session_state.current](st.session_state.current)


st.set_page_config(page_title="AutoTestDesign", layout="wide")
main()
