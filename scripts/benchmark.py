"""
benchmark.py  --  Measure pipeline latency and LLM token usage.

Produces a single, reproducible source of truth for every performance and
cost figure cited in the project reports. Run it and it writes
``docs/benchmark_report.md``.

What it measures
----------------
1. Per-stage latency of the deterministic rule pipeline (parse, risk,
   coverage, test-case generation, oracle attach, optimise, export),
   averaged over N repeats. This path is what the assignment's
   "<= 2s generation" requirement should be judged against, because it
   is network-independent and reproducible.
2. LLM token usage and latency for the two model-backed stages
   (requirement parsing, risk analysis), if an API key is configured.
   Token counts come straight from the provider's ``usage`` field, so
   the cost figures are exact.

Run
---
    .venv/bin/python scripts/benchmark.py            # full run
    .venv/bin/python scripts/benchmark.py --repeats 10
    .venv/bin/python scripts/benchmark.py --no-llm   # skip LLM stages
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from core import (  # noqa: E402
    coverage_analysis,
    exporter,
    optimizer,
    oracle as oracle_mod,
    pipeline_fallback,
    testcase_generator,
)

REQUIREMENTS_PATH = PROJECT_ROOT / "data" / "mini_ecommerce_requirements.json"
OUTPUT_DOC = PROJECT_ROOT / "docs" / "benchmark_report.md"
# qwen3.6-flash list price (0 < tokens <= 256K tier), CNY per 1M tokens.
PRICE_INPUT_PER_M = 1.2
PRICE_OUTPUT_PER_M = 7.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_raw_text() -> Tuple[str, Dict[str, Any]]:
    canon = json.loads(REQUIREMENTS_PATH.read_text(encoding="utf-8"))
    lines = []
    for r in canon["requirements"]:
        sentence = (r.get("expected_behavior") or [r.get("feature", "")])[0]
        lines.append(f"{r['requirement_id']}: {sentence}")
    return "\n".join(lines), canon


def _timed(fn: Callable[[], Any], repeats: int) -> Tuple[Any, List[float]]:
    """Run fn `repeats` times; return (last_result, [elapsed_ms,...])."""
    times: List[float] = []
    result = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return result, times


def _stat(times: List[float]) -> Dict[str, float]:
    return {
        "mean_ms": round(statistics.mean(times), 3),
        "min_ms": round(min(times), 3),
        "max_ms": round(max(times), 3),
        "stdev_ms": round(statistics.pstdev(times), 3) if len(times) > 1 else 0.0,
    }


# ---------------------------------------------------------------------------
# Rule-pipeline latency
# ---------------------------------------------------------------------------

def benchmark_rule_pipeline(raw: str, canon: Dict[str, Any],
                            repeats: int) -> Dict[str, Any]:
    stages: Dict[str, Dict[str, float]] = {}

    req_df, t = _timed(lambda: pipeline_fallback.parse_requirements(raw), repeats)
    stages["parse (rule)"] = _stat(t)

    parsed, t = _timed(
        lambda: pipeline_fallback.parse_requirements_struct(raw), repeats)
    stages["structure (rule)"] = _stat(t)

    risk_df, t = _timed(
        lambda: pipeline_fallback.analyze_risk(req_df), repeats)
    stages["risk (rule)"] = _stat(t)

    cov_json, t = _timed(
        lambda: coverage_analysis.generate_coverage(parsed), repeats)
    stages["coverage"] = _stat(t)

    risk_json = pipeline_fallback.risk_df_to_engine_json(risk_df)
    tc_result, t = _timed(
        lambda: testcase_generator.generate_test_cases(cov_json, risk_json),
        repeats)
    stages["test-case generation"] = _stat(t)

    cases = tc_result["test_cases"]

    def _attach():
        # copy so repeated runs are independent
        local = [dict(c) for c in cases]
        for c in local:
            c.pop("oracle", None)
        oracle_mod.attach_oracles(local, canon["requirements"])
        return local
    _, t = _timed(_attach, repeats)
    stages["oracle attach"] = _stat(t)

    _, t = _timed(
        lambda: optimizer.optimize_test_suite(tc_result, risk_json,
                                              minimize=True),
        repeats)
    stages["optimise (minimise)"] = _stat(t)

    out_dir = PROJECT_ROOT / "outputs" / "_bench_tmp"
    _, t = _timed(
        lambda: exporter.export_all(req_df, risk_df,
                                    pipeline_fallback.coverage_dataframe(
                                        cov_json, risk_df),
                                    tc_result, output_dir=str(out_dir)),
        repeats)
    stages["export (CSV/JSON/Excel)"] = _stat(t)

    # The "generation" requirement covers parse->coverage->test cases.
    gen_mean = sum(stages[k]["mean_ms"] for k in (
        "parse (rule)", "structure (rule)", "risk (rule)", "coverage",
        "test-case generation", "oracle attach"))

    return {
        "stages": stages,
        "n_requirements": len(req_df),
        "n_test_cases": tc_result["summary"]["total"],
        "end_to_end_generation_mean_ms": round(gen_mean, 3),
    }


# ---------------------------------------------------------------------------
# LLM token usage + latency
# ---------------------------------------------------------------------------

def benchmark_llm(canon: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not os.getenv("API_KEY"):
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    client = OpenAI(api_key=os.getenv("API_KEY"),
                    base_url=os.getenv("BASE_URL"))
    model = os.getenv("MODEL", "")
    prompts_dir = PROJECT_ROOT / "prompts"
    parser_prompt = (prompts_dir / "parser_prompt.txt").read_text(encoding="utf-8")
    risk_prompt = (prompts_dir / "risk_prompt.txt").read_text(encoding="utf-8")

    def _call(system: str, user: str) -> Tuple[float, Any]:
        t0 = time.perf_counter()
        resp = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return (time.perf_counter() - t0) * 1000.0, resp.usage

    # One batch parse call
    raw = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    parse_ms, parse_usage = _call(parser_prompt,
                                  "Parse these requirements:\n" + raw)

    # One risk call per requirement (mirrors core/risk_analysis.analyze_risks)
    risk_latencies: List[float] = []
    risk_in = risk_out = 0
    for r in canon["requirements"]:
        payload = json.dumps({
            "requirement_id": r["requirement_id"],
            "feature": r.get("feature", ""),
            "expected_behavior": r.get("expected_behavior", []),
        })
        ms, usage = _call(risk_prompt, payload)
        risk_latencies.append(ms)
        risk_in += usage.prompt_tokens
        risk_out += usage.completion_tokens

    total_in = parse_usage.prompt_tokens + risk_in
    total_out = parse_usage.completion_tokens + risk_out
    cost_std = (total_in * PRICE_INPUT_PER_M
                + total_out * PRICE_OUTPUT_PER_M) / 1_000_000
    cost_batch = cost_std / 2

    return {
        "model": model,
        "parse": {
            "latency_ms": round(parse_ms, 1),
            "input_tokens": parse_usage.prompt_tokens,
            "output_tokens": parse_usage.completion_tokens,
        },
        "risk": {
            "calls": len(risk_latencies),
            "latency_mean_ms": round(statistics.mean(risk_latencies), 1),
            "input_tokens": risk_in,
            "output_tokens": risk_out,
        },
        "totals": {
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "cost_cny_standard": round(cost_std, 4),
            "cost_cny_batch": round(cost_batch, 4),
        },
    }


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_report(rule: Dict[str, Any], llm: Optional[Dict[str, Any]],
                  repeats: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    import platform
    L: List[str] = []
    L.append("# Benchmark Report")
    L.append("")
    L.append("## Abstract")
    L.append("")
    L.append("This report records reproducible performance and cost "
             "measurements for the AutoTestDesign pipeline. The "
             "deterministic rule path is measured for per-stage latency, "
             "and the language-model-backed stages are measured for "
             "token usage and cost when an API key is configured. Every "
             "figure cited in [test_plan.md](test_plan.md) and "
             "[cost_estimation.md](cost_estimation.md) traces back to "
             "this document. The report is regenerated by "
             "[scripts/benchmark.py](../scripts/benchmark.py).")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Provenance")
    L.append("")
    L.append(f"- Generated at: {now}")
    L.append(f"- Host: Python {platform.python_version()} on "
             f"{platform.system()} {platform.machine()}")
    L.append(f"- Repetitions per stage: {repeats}")
    L.append(f"- Requirements measured: {rule['n_requirements']}; "
             f"test cases produced: {rule['n_test_cases']}.")
    L.append("")
    L.append("---")
    L.append("")

    # --- performance requirement verdict --------------------------------
    gen = rule["end_to_end_generation_mean_ms"]
    verdict = "MET" if gen <= 2000 else "NOT MET"
    L.append("## 1. Performance Requirement Verdict")
    L.append("")
    L.append("The assignment targets test-case generation in under two "
             "seconds. The verdict is computed against the deterministic "
             "rule path (parse → structure → risk → coverage → test-case "
             "generation → oracle), which is network-independent and "
             "reproducible. The measured end-to-end generation latency on "
             f"the rule path is {gen:.1f} ms for {rule['n_requirements']} "
             f"requirements yielding {rule['n_test_cases']} cases. The "
             f"two-second target is therefore **{verdict}**.")
    L.append("")
    L.append("The language-model-backed parse and risk stages reported "
             "in §3 incur network latency and are not counted against the "
             "generation budget; they execute once per session and fall "
             "back to the rule path when unavailable.")
    L.append("")
    L.append("---")
    L.append("")

    # --- rule stage table ----------------------------------------------
    L.append("## 2. Rule-Pipeline Stage Latency")
    L.append("")
    L.append("Per-stage latency is recorded in Table 1 and is averaged "
             f"over {repeats} repetitions. The rule pipeline is "
             "deterministic, so latencies are stable across runs.")
    L.append("")
    L.append("**Table 1.** Rule-pipeline stage latency.")
    L.append("")
    L.append("| Stage | Mean (ms) | Min (ms) | Max (ms) | Stdev (ms) |")
    L.append("|---|---:|---:|---:|---:|")
    for name, s in rule["stages"].items():
        L.append(f"| {name} | {s['mean_ms']} | {s['min_ms']} | "
                 f"{s['max_ms']} | {s['stdev_ms']} |")
    L.append("")
    L.append("---")
    L.append("")

    # --- LLM section ----------------------------------------------------
    L.append("## 3. LLM Token Usage and Cost")
    L.append("")
    if llm is None:
        L.append("No API key was configured at benchmark time, so the "
                 "language-model-backed stages were not measured. When a "
                 "key is configured, this section records exact token "
                 "counts from the provider's `usage` field together with "
                 "the derived cost.")
        L.append("")
    else:
        t = llm["totals"]
        L.append(f"The model invoked is `{llm['model']}` with "
                 "`temperature=0`. Token counts are read directly from "
                 "the provider's `usage` field and are therefore exact. "
                 "Per-call counts are recorded in Table 2.")
        L.append("")
        L.append("**Table 2.** LLM call counts, latency, and token "
                 "usage per session.")
        L.append("")
        L.append("| Call | Count | Latency (ms) | Input tokens | Output tokens |")
        L.append("|---|---:|---:|---:|---:|")
        L.append(f"| Requirement parse (batch) | 1 | "
                 f"{llm['parse']['latency_ms']} | "
                 f"{llm['parse']['input_tokens']} | "
                 f"{llm['parse']['output_tokens']} |")
        L.append(f"| Risk analysis (per requirement) | "
                 f"{llm['risk']['calls']} | "
                 f"{llm['risk']['latency_mean_ms']} (mean) | "
                 f"{llm['risk']['input_tokens']} | "
                 f"{llm['risk']['output_tokens']} |")
        L.append(f"| **Total per session** | | | "
                 f"**{t['input_tokens']}** | **{t['output_tokens']}** |")
        L.append("")
        L.append("### 3.1 Cost per Full Pipeline Run")
        L.append("")
        L.append("At list price "
                 f"(¥{PRICE_INPUT_PER_M} per 1 M input tokens, "
                 f"¥{PRICE_OUTPUT_PER_M} per 1 M output tokens), the "
                 "session cost is recorded in Table 3.")
        L.append("")
        L.append("**Table 3.** Cost per session.")
        L.append("")
        L.append("| Pricing mode | Cost (CNY) |")
        L.append("|---|---:|")
        L.append(f"| Standard | ¥{t['cost_cny_standard']} |")
        L.append(f"| Batch (half price) | ¥{t['cost_cny_batch']} |")
        L.append("")
        L.append(f"A complete run consumes {t['total_tokens']} tokens, "
                 f"costing approximately ¥{t['cost_cny_standard']} at "
                 "list price. Even after dozens of interactive "
                 "iterations the cumulative LLM cost is immaterial in "
                 "comparison with labour cost.")
        L.append("")
    L.append("---")
    L.append("")

    L.append("## 4. Notes")
    L.append("")
    L.append("The coverage, test-case-generation, oracle-synthesis, and "
             "optimisation stages issue no language-model calls and "
             "contribute zero token cost; they are deterministic rule "
             "engines. Latency depends on the host machine, so this "
             "report is regenerated on the demonstration host for "
             "presentation-accurate figures. Temporary export artefacts "
             "written during benchmarking are persisted under "
             "[outputs/_bench_tmp/](../outputs/_bench_tmp/) and may be "
             "deleted after each run.")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    raw, canon = _load_raw_text()
    print(f"Benchmarking rule pipeline ({args.repeats} repeats)...")
    rule = benchmark_rule_pipeline(raw, canon, args.repeats)
    print(f"  end-to-end generation: "
          f"{rule['end_to_end_generation_mean_ms']:.1f} ms")

    llm = None
    if not args.no_llm:
        print("Benchmarking LLM stages (this makes real API calls)...")
        llm = benchmark_llm(canon)
        if llm is None:
            print("  skipped (no API key / openai unavailable)")
        else:
            print(f"  total tokens: {llm['totals']['total_tokens']}, "
                  f"cost ¥{llm['totals']['cost_cny_standard']}")

    OUTPUT_DOC.write_text(render_report(rule, llm, args.repeats),
                          encoding="utf-8")
    print(f"Wrote {OUTPUT_DOC.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
