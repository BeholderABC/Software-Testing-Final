# Prompt Design

## Abstract

This document records the design of the prompts used to drive the
language-model components of AutoTestDesign. Two stages of the
pipeline invoke a model: requirement parsing and risk analysis. Both
prompts are engineered for strict, deterministic, schema-compliant
JSON output, and both are supported by a deterministic fallback so
that the pipeline completes whether or not the model is reachable.
The design principles applied — strict output schema, controlled
vocabulary, determinism, few-shot grounding, and a fault-tolerant
fallback — are recorded below and motivated.

---

## 1. Introduction

The two tasks delegated to the language model — extracting a
structured representation of a natural-language requirement, and
producing a multi-dimensional risk judgement — share three properties
that make them appropriate for an LLM: each requires natural-language
understanding; each benefits from broad world knowledge; and each
admits a sufficiently small, schema-controlled output that the result
can be consumed by deterministic downstream code. Every subsequent
stage of the pipeline (coverage analysis, test-case generation,
oracle synthesis, optimisation, export, execution) is implemented as a
deterministic rule engine, both because those stages do not require
linguistic understanding and because their reproducibility is
important to the auditability of the suite.

---

## 2. Where the Language Model is Used

**Table 1.** LLM use across the pipeline.

| Stage | Module | Prompt | Justification |
|---|---|---|---|
| Requirement parsing | [core/parser.py](../core/parser.py) | `parser_prompt.txt` | Natural-language understanding — extracting fields and structured constraint types from free text. |
| Risk analysis | [core/risk_analysis.py](../core/risk_analysis.py) | `risk_prompt.txt` | Subjective multi-dimensional judgement — weighing business impact, failure probability, complexity, and failure impact. |

No other stage invokes the model. The files
`prompts/coverage_prompt.txt` and `prompts/testcase_prompt.txt` are
preserved as documented fallbacks in case a future variant of the tool
wishes to enrich the rule-generated artefacts with a model rewrite;
they are not on the active path.

---

## 3. Design Principles

### 3.1 Strict single-object JSON output

Each prompt instructs the model to return one JSON object with no
Markdown fencing and no commentary. The post-processing helper
[core/utils.py:extract_json](../core/utils.py) provides a defensive
strip in case the constraint is occasionally violated, but the prompt
is responsible for satisfying it in the common case.

### 3.2 Controlled vocabulary

The parser prompt pins the constraint vocabulary to a closed set of
nine lowercase types (`length`, `unique`, `existence`, `required`,
`charset`, `pattern`, `enum`, `numeric_range`, `relational`) and
prohibits historical synonyms in explicit terms. This keeps the LLM
output byte-compatible with the rule engines that consume it.

### 3.3 Determinism

Both invocations use `temperature=0`. The prompts close with an
explicit instruction to be deterministic. The risk prompt additionally
fixes the score-to-level mapping (1–3 ⇒ Low, 4–7 ⇒ Medium, 8–10 ⇒
High) so that the model cannot drift, and instructs the model to
report only the four per-dimension ratings; the headline score is
computed from the ratings by the consumer, so the score is a
transparent function of the dimensions.

### 3.4 Few-shot grounding

Each prompt closes with one worked input–output example. The example
demonstrates the exact JSON shape, the controlled vocabulary, and the
expected granularity of the output. Empirically, this has been
observed to improve first-pass schema compliance.

### 3.5 Schema as the contract

The prompts emit the same schema-v1 documented in
[STYLE_GUIDE.md](STYLE_GUIDE.md) §3. Because the contract lives in
one place, the LLM path and the rule fallback produce identical
shapes; downstream stages never need to branch on the source.

---

## 4. The Parser Prompt

`parser_prompt.txt` converts a batch of natural-language requirements
into structured JSON. Its principal elements are: a behavioural
preamble (return only JSON; preserve given identifiers; split
independent requirements; express constraints structurally); a
declared output schema; the catalogue of allowed constraint types
with their exact field layouts; explicit prohibition of historical
synonyms; and a worked few-shot example for REQ-007 and REQ-009.

A live invocation on REQ-009 produces a `relational` constraint
(`quantity <= stock`) with the canonical identifier format. This is
exactly the constraint type expected by the coverage engine, and is
the shape that drives the boundary trio recorded in
[detailed_test_design_execution.md](detailed_test_design_execution.md)
§2.

---

## 5. The Risk Prompt

`risk_prompt.txt` rates one structured requirement on four
dimensions. Its principal elements are: the four dimensions to be
rated; the fixed score-to-level mapping; the declared output schema
(four per-dimension ratings plus a list of one-sentence
justifications); and a worked few-shot example for REQ-009.

The justification array is required to use the same word
(*low / medium / high*) as the corresponding numeric rating implies,
so that prose and numbers cannot drift apart. The complete twelve-
requirement run is persisted at
[data/baseline/risk_llm.json](../data/baseline/risk_llm.json) and
underwrites [risk_analysis_report.md](risk_analysis_report.md).

---

## 6. Robustness and Fallback

The LLM path is wrapped so that no failure can break the workflow.
The four distinct failure modes and their responses are listed in
Table 2.

**Table 2.** Failure modes and the response of the pipeline.

| Failure mode | Response |
|---|---|
| No API key configured | The Streamlit scheduler checks `API_KEY` at start-up and uses the rule pipeline directly. |
| Import failure | If the `openai` package is not importable, the user interface sets `_LLM_AVAILABLE = False` and falls back. |
| Per-call failure | `parse_with_fallback` and `analyse_risk_with_fallback` catch any exception, surface a warning, and continue on the rule path. |
| Per-item failure in batch risk | [core/risk_analysis.py:analyze_risks](../core/risk_analysis.py) catches a single requirement's failure and substitutes a Medium / 5 default without aborting the batch. |

The active path is always displayed in the sidebar of the user
interface, so a reviewer can see whether a given run used the LLM or
the deterministic fallback.

---

## 7. Operational Notes

Configuration resides in `.env` (variables `API_KEY`, `BASE_URL`,
`MODEL`). Any OpenAI-protocol endpoint is supported because the
client is constructed with a configurable `base_url`. Cost is
controlled by `temperature=0` and a tight prompt that bounds output
length; the budget is reported in
[cost_estimation.md](cost_estimation.md). When the host shell exports
a SOCKS proxy, the OpenAI SDK requires the `httpx[socks]` extra; this
is pinned in `requirements.txt`.

---

## 8. Conclusion

The prompt design enforces a strict, deterministic, schema-compliant
contract between the language model and the deterministic downstream
engines. The design supports reproducibility of every artefact, an
auditable controlled vocabulary, and graceful degradation to a
deterministic fallback whenever the model is unavailable.

---

## References

- ISO/IEC/IEEE 29119-1:2022, *Software and systems engineering — Software testing — Part 1: General concepts*.
