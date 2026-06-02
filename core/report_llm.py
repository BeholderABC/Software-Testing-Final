"""
report_llm.py  --  LLM-backed Markdown report generation.

Given a compact JSON payload assembled from the pipeline artefacts, this
module asks the configured chat model to *write* one of the three
deliverable documents (risk analysis report, test plan, detailed test
design & execution) as IEEE 829-structured Markdown. The narrative is
the model's; every fact comes from the payload (the prompts forbid
invention).

It deliberately mirrors the conventions already used by
``core/parser.py`` / ``core/risk_analysis.py``: an OpenAI-compatible
client configured from ``API_KEY`` / ``BASE_URL`` / ``MODEL`` in
``.env``, ``temperature=0`` for reproducibility, and one prompt file per
task under ``prompts/``.

Each call is wall-clock timed and returns the model's token usage so the
caller can report the real generation cost (see
``core/report_pipeline.py``). When no key is configured, or the SDK is
absent, importing/using this module raises and the caller falls back to
the deterministic rule generator in ``core/report_generator.py``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# The OpenAI SDK and dotenv are optional at import time so the rule
# fallback keeps working in a minimal environment.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass

try:
    from openai import OpenAI
    _SDK_AVAILABLE = True
except Exception:  # pragma: no cover - SDK optional
    OpenAI = None  # type: ignore
    _SDK_AVAILABLE = False

_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

# prompt file per document kind.
PROMPT_FILES = {
    "risk_analysis_report": "risk_report_prompt.txt",
    "test_plan": "test_plan_prompt.txt",
    "detailed_test_design_execution": "detailed_design_prompt.txt",
}


def has_llm() -> bool:
    """True when a live model call can be attempted."""
    return _SDK_AVAILABLE and bool(os.getenv("API_KEY"))


def model_name() -> str:
    return os.getenv("MODEL", "unknown-model")


def _client() -> "OpenAI":
    if not has_llm():
        raise RuntimeError("LLM not configured (missing SDK or API_KEY)")
    return OpenAI(api_key=os.getenv("API_KEY"), base_url=os.getenv("BASE_URL"))


def _strip_fences(text: str) -> str:
    """Drop a leading/trailing ```/```markdown fence if the model wrapped
    the whole document in one despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip() + "\n"


def generate_document(kind: str, payload: Dict[str, Any],
                      *, timeout: Optional[float] = 120.0
                      ) -> Tuple[str, float, Dict[str, int]]:
    """Generate one document with the LLM.

    Returns ``(markdown, elapsed_seconds, usage)`` where ``usage`` holds
    ``prompt_tokens`` / ``completion_tokens`` / ``total_tokens`` (zeros
    when the backend does not report usage). Raises on any failure so the
    caller can fall back to the rule generator.
    """
    if kind not in PROMPT_FILES:
        raise ValueError(f"Unknown document kind: {kind}")
    system_prompt = (_PROMPTS / PROMPT_FILES[kind]).read_text(encoding="utf-8")

    client = _client()
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model_name(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",
             "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - started

    content = response.choices[0].message.content or ""
    markdown = _strip_fences(content)
    if len(markdown) < 80:
        raise RuntimeError("LLM returned an implausibly short document")

    usage_obj = getattr(response, "usage", None)
    usage = {
        "prompt_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
        "completion_tokens": int(
            getattr(usage_obj, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage_obj, "total_tokens", 0) or 0),
    }
    if usage["total_tokens"] == 0:
        usage["total_tokens"] = (
            usage["prompt_tokens"] + usage["completion_tokens"])
    return markdown, elapsed, usage
