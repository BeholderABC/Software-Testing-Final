"""
report_pipeline.py  --  Orchestrate LLM-or-rule report generation.

For each of the three deliverable documents this module:

  1. assembles a compact JSON payload from the pipeline artefacts;
  2. asks the LLM to write the document (``core/report_llm.py``),
     wall-clock timing the call and capturing token usage;
  3. on missing key or any error, falls back to the deterministic rule
     generator (``core/report_generator.py``), timing that instead;
  4. after all documents are written, replaces the ``METRICS_MARKER``
     placeholder in each with a tool-measured block reporting the
     generation time and token cost (the chicken-and-egg figures that
     can only be known *after* generation).

The return value carries both the written paths and the per-document
metrics so the UI can show what happened.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from core import report_generator as rg
from core import report_llm

# Blended list-price token rate (¥ per 1000 tokens), overridable via env.
# Defaults to a qwen-flash-class rate; only affects the cost line.
DEFAULT_TOKEN_RATE_PER_1K = 0.0008


def _token_rate() -> float:
    try:
        return float(os.getenv("LLM_PRICE_PER_1K_TOKENS",
                               DEFAULT_TOKEN_RATE_PER_1K))
    except (TypeError, ValueError):
        return DEFAULT_TOKEN_RATE_PER_1K


# ---------------------------------------------------------------------------
# Payload builders (compact JSON fed to the LLM)
# ---------------------------------------------------------------------------

def _req_rows(requirements: Any) -> List[Dict[str, Any]]:
    return [{"requirement_id": r.get("requirement_id"),
             "feature": rg._feature_of(r),
             "target_module": r.get("target_module")}
            for r in rg._records(requirements)]


def _risk_payload(requirements: Any, risk: Any,
                  meta: Dict[str, Any],
                  pipeline_timings: Optional[List[Dict[str, Any]]]
                  ) -> Dict[str, Any]:
    risks = rg._records(risk)
    return {
        "target_app": meta.get("target_app", rg.DEFAULT_TARGET_APP),
        "run_id": meta.get("run_id"),
        "requirements": _req_rows(requirements),
        "risk": [{k: r.get(k) for k in (
            "requirement_id", "business_impact", "failure_probability",
            "complexity", "failure_impact", "risk_score", "risk_level",
            "risk_reason")} for r in risks],
        "pipeline_timings": pipeline_timings or [],
    }


def _suites(requirements: Any, risk: Any, test_cases: Any
            ) -> List[Dict[str, Any]]:
    reqs = rg._records(requirements)
    cases = rg._records(test_cases)
    level_by_req = {r.get("requirement_id"): rg._norm_level(
        r.get("risk_level") or r.get("priority"))
        for r in rg._records(risk)}
    out = []
    for mod, ids in rg._module_index(reqs).items():
        out.append({
            "module": mod, "requirement_ids": ids,
            "risk_levels": sorted({level_by_req.get(i, "—") for i in ids}),
            "techniques": rg._techniques_for_reqs(cases, ids)})
    return out


def _run_modes(runs: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for r in runs or []:
        s = r.get("summary")
        out.append({
            "source": r.get("source"), "http_mode": r.get("http_mode"),
            "generated": r.get("generated_count"),
            "executed": r.get("executed_count"),
            "passed": getattr(s, "passed", None),
            "failed": getattr(s, "failed", None),
            "skipped": getattr(s, "skipped", None),
            "seconds": round(float(getattr(s, "duration_seconds", 0) or 0), 2)})
    return out


def _test_plan_payload(requirements, risk, coverage, test_cases, test_summary,
                       optimization_summary, runs, meta,
                       pipeline_timings) -> Dict[str, Any]:
    return {
        "target_app": meta.get("target_app", rg.DEFAULT_TARGET_APP),
        "run_id": meta.get("run_id"),
        "requirements": _req_rows(requirements),
        "risk": [{"requirement_id": r.get("requirement_id"),
                  "risk_level": rg._norm_level(
                      r.get("risk_level") or r.get("priority")),
                  "risk_score": r.get("risk_score")}
                 for r in rg._records(risk)],
        "coverage_count": len(rg._records(coverage)),
        "test_summary": test_summary or {"total": len(rg._records(test_cases))},
        "suites": _suites(requirements, risk, test_cases),
        "optimization_summary": optimization_summary,
        "run_modes": _run_modes(runs),
        "frameworks": [
            {"name": "PyTest", "used_for": "Test execution",
             "rationale": "Python standard; parametrize drives the "
                          "data-driven harness."},
            {"name": "requests", "used_for": "HTTP calls",
             "rationale": "Simple, explicit REST client."},
            {"name": "Django REST Framework", "used_for": "System under test",
             "rationale": "The target application's framework."},
            {"name": "Streamlit", "used_for": "Tool UI",
             "rationale": "Interactive review of editable artefacts."}],
        "org_roles": [
            {"role": "Test lead",
             "responsibilities": "Plan ownership, risk sign-off, scheduling"},
            {"role": "Tool / pipeline",
             "responsibilities": "Parsing, risk, coverage, test-design"},
            {"role": "User interface",
             "responsibilities": "Streamlit workflow, export, runner"},
            {"role": "Target application",
             "responsibilities": "Backend, harness, defect repair"},
            {"role": "Documentation",
             "responsibilities": "Reports, traceability, packaging"}],
        "pipeline_timings": pipeline_timings or [],
    }


def _detailed_payload(requirements, risk, coverage, test_cases, run_summary,
                      runs, meta) -> Dict[str, Any]:
    reqs = rg._records(requirements)
    risks = rg._records(risk)
    module = rg._focus_module(reqs, risks)
    id_set = {str(r.get("requirement_id", "?")) for r in reqs
              if str(r.get("target_module") or "General") == module}

    tech_counts: Dict[str, int] = {}
    box_counts = {"black-box": 0, "white-box": 0}
    case_rows = []
    for c in rg._records(test_cases):
        if str(c.get("requirement_id", "")) not in id_set:
            continue
        tech = str(c.get("test_design_technique", "—"))
        ctype = str(c.get("coverage_type", "")).lower()
        tech_counts[tech] = tech_counts.get(tech, 0) + 1
        box = ("white-box" if tech == rg._WHITE_BOX_TECHNIQUE
               else rg._TYPE_TECHNIQUE.get(ctype, ("", "black-box"))[1])
        box_counts[box] = box_counts.get(box, 0) + 1
        case_rows.append({
            "test_case_id": c.get("test_case_id"),
            "requirement_id": c.get("requirement_id"),
            "test_design_technique": tech, "coverage_type": ctype,
            "box": box,
            "description": rg._stringify(c.get("description"), 90),
            "expected_result": rg._stringify(c.get("expected_result"), 80)})

    canon = []
    for r in rg._run_results(run_summary):
        rid = str(getattr(r, "requirement_id", ""))
        if id_set and rid not in id_set:
            continue
        canon.append({
            "test_case_id": getattr(r, "test_case_id", "?"),
            "requirement_id": rid,
            "coverage_type": getattr(r, "coverage_type", "—"),
            "outcome": getattr(r, "outcome", "—"),
            "message": rg._stringify(getattr(r, "message", ""), 80)})

    feat = {r.get("requirement_id"): rg._feature_of(r) for r in reqs}
    return {
        "target_app": meta.get("target_app", rg.DEFAULT_TARGET_APP),
        "run_id": meta.get("run_id"), "focus_module": module,
        "module_requirements": [
            {"requirement_id": rid, "feature": feat.get(rid, "—")}
            for rid in (str(r.get("requirement_id", "?")) for r in reqs)
            if rid in id_set],
        "coverage_items": [
            {"coverage_item": c.get("coverage_item"),
             "requirement_id": c.get("requirement_id"),
             "coverage_type": c.get("coverage_type"),
             "coverage_strategy": c.get("coverage_strategy")}
            for c in rg._records(coverage)
            if str(c.get("requirement_id", "")) in id_set],
        "test_cases": case_rows,
        "technique_counts": tech_counts, "box_counts": box_counts,
        "run_modes": _run_modes(runs), "canonical_results": canon,
    }


# ---------------------------------------------------------------------------
# Metrics block
# ---------------------------------------------------------------------------

def _render_metrics(metrics: Dict[str, Dict[str, Any]]) -> str:
    """Render the tool-measured generation-metrics block injected in place
    of ``METRICS_MARKER``."""
    rate = _token_rate()
    rows, gen_total, tok_total = [], 0.0, 0
    for doc, m in metrics.items():
        gen_total += m["seconds"]
        tok_total += m["total_tokens"]
        rows.append([doc, m["engine"], round(m["seconds"], 3),
                     m["prompt_tokens"], m["completion_tokens"],
                     m["total_tokens"]])
    rows.append(["**Total**", "", round(gen_total, 3), "", "", tok_total])
    cost = tok_total / 1000.0 * rate
    table = rg._md_table(
        ["Document", "Engine", "Gen time (s)", "Prompt tok", "Completion tok",
         "Total tok"], rows, aligns=["l", "l", "r", "r", "r", "r"])
    return (table + f"\n\nEstimated LLM token cost: **¥{cost:.4f}** at "
            f"¥{rate:g} / 1k tokens"
            + (f" (model `{report_llm.model_name()}`)."
               if tok_total else " (rule fallback used — no tokens consumed)."))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

# kind -> (filename, rule generator callable factory)
_FILENAMES = {
    "risk_analysis_report": "risk_analysis_report.md",
    "test_plan": "test_plan.md",
    "detailed_test_design_execution": "detailed_test_design_execution.md",
}


def _llm_banner(meta: Dict[str, Any]) -> str:
    when = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"> _Auto-generated by **AutoTestDesign** (LLM: "
        f"`{report_llm.model_name()}`) for run "
        f"`{meta.get('run_id', '?')}` on {when}._\n"
        f"> _Target application: "
        f"**{meta.get('target_app', rg.DEFAULT_TARGET_APP)}**._\n\n")


def generate_reports(requirements: Any, risk: Any, coverage: Any,
                     test_cases: Any, docs_dir: str, *,
                     test_summary: Optional[Dict[str, Any]] = None,
                     optimization_summary: Optional[Dict[str, Any]] = None,
                     run_summary: Any = None,
                     runs: Optional[List[Dict[str, Any]]] = None,
                     pipeline_timings: Optional[List[Dict[str, Any]]] = None,
                     meta: Optional[Dict[str, Any]] = None,
                     prefer_llm: bool = True) -> Dict[str, Any]:
    """Generate the three reports (LLM with rule fallback) and write them.

    Returns ``{"paths": {kind: path}, "metrics": {kind: {...}},
    "engine_by_doc": {kind: 'LLM'|'rule'}}``.
    """
    os.makedirs(docs_dir, exist_ok=True)
    meta = dict(meta or {})
    meta.setdefault("generated_at",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    use_llm = prefer_llm and report_llm.has_llm()

    # Per-kind: the LLM payload and the rule-fallback thunk.
    payloads = {
        "risk_analysis_report":
            _risk_payload(requirements, risk, meta, pipeline_timings),
        "test_plan":
            _test_plan_payload(requirements, risk, coverage, test_cases,
                               test_summary, optimization_summary, runs, meta,
                               pipeline_timings),
        "detailed_test_design_execution":
            _detailed_payload(requirements, risk, coverage, test_cases,
                              run_summary, runs, meta),
    }
    rule_thunks = {
        "risk_analysis_report":
            lambda: rg.generate_risk_analysis_report(requirements, risk, meta),
        "test_plan":
            lambda: rg.generate_test_plan(
                requirements, risk, coverage, test_cases, test_summary,
                optimization_summary, runs, meta, pipeline_timings),
        "detailed_test_design_execution":
            lambda: rg.generate_detailed_design(
                requirements, risk, coverage, test_cases, run_summary, meta,
                runs),
    }

    contents: Dict[str, str] = {}
    metrics: Dict[str, Dict[str, Any]] = {}
    engine_by_doc: Dict[str, str] = {}

    for kind in _FILENAMES:
        md, engine, seconds, usage = None, "rule", 0.0, {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if use_llm:
            try:
                md, seconds, usage = report_llm.generate_document(
                    kind, payloads[kind])
                md = _llm_banner(meta) + md
                engine = "LLM"
            except Exception:
                md = None  # fall through to rule
        if md is None:
            started = time.perf_counter()
            md = rule_thunks[kind]()
            seconds = time.perf_counter() - started
            engine = "rule"
        contents[kind] = md
        engine_by_doc[kind] = engine
        metrics[kind] = {"engine": engine, "seconds": seconds, **usage}

    # Inject the measured generation metrics into any doc carrying the
    # marker (test plan + detailed design).
    metrics_md = _render_metrics(metrics)
    paths: Dict[str, str] = {}
    for kind, content in contents.items():
        if rg.METRICS_MARKER in content:
            content = content.replace(rg.METRICS_MARKER, metrics_md)
        path = os.path.join(docs_dir, _FILENAMES[kind])
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        paths[kind] = path

    return {"paths": paths, "metrics": metrics, "engine_by_doc": engine_by_doc}
