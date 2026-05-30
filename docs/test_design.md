# Test Design

## Abstract

This document records the design of the test-case generation engines
shipped with AutoTestDesign. Both a black-box engine, applying
equivalence partitioning, boundary value analysis, and decision-table
testing, and a white-box engine, applying state-transition testing,
are implemented. Each engine produces structured test cases carrying
full traceability and a machine-checkable test oracle. A
risk-based optimiser orders and reduces the resulting suite. The
description below traces every component to the technique vocabulary
of ISO/IEC/IEEE 29119-4 and to the foundation-level test process of
ISTQB.

---

## 1. Introduction

A test design engine is the component of a test-design tool that
converts identified coverage items into executable test cases. The
present engines are implemented as deterministic rule engines rather
than as language-model invocations, because the conversion is
algorithmic and the reproducibility of the resulting suite is required
for auditability. The engines are realised in the modules listed in
Table 1.

**Table 1.** Engine modules.

| Concern | Module |
|---|---|
| Black-box test-case generation | [core/testcase_generator.py](../core/testcase_generator.py) |
| White-box state-transition coverage | [core/state_model.py](../core/state_model.py) |
| Oracle synthesis | [core/oracle.py](../core/oracle.py) |
| Suite optimisation | [core/optimizer.py](../core/optimizer.py) |

The internal verification of these engines is recorded in the unit
suite [`tests/unit/`](../tests/unit/), comprising forty-eight cases.

---

## 2. Position within the Pipeline

The test design engines occupy the middle of the AutoTestDesign
pipeline. Figure 1 summarises the data flow.

```
requirement text ── parser ─▶ structured requirement
                  └─ risk ─▶ risk assessment
                  └─ coverage ─▶ coverage items
                                  │
                                  ▼
                         test design engines
                                  │
                  ┌───────────────┼────────────────┐
                  ▼               ▼                ▼
            EP / BVA / DT   state transition  oracle synthesis
                  │               │                │
                  └───────────────┼────────────────┘
                                  ▼
                         risk-based optimiser
                                  │
                                  ▼
                          test_cases.json
```

*Figure 1.* Position of the design engines within the pipeline.

The coverage stage decides *what scenarios must be verified*. The
design stage converts each scenario into an executable, traceable
test case carrying a structured oracle. The optimisation stage orders
the suite and optionally reduces it. The engines are deterministic:
identical input yields identical output.

---

## 3. Inputs and Outputs

### 3.1 Inputs

- *Coverage JSON*: accepts either `{"coverages": [...]}` (the
  canonical form) or `{"coverage": [...]}` (legacy fixtures).
- *Risk JSON*: the `risk_assessment` list indexed by
  `requirement_id`. Missing risk data is tolerated and defaults to
  `risk_level = Medium`, `risk_score = 5`.

### 3.2 Output

```jsonc
{
  "test_cases": [ /* one structured test case per item */ ],
  "summary": {
    "total": 61,
    "by_technique": {
      "Equivalence Partitioning": 22,
      "Boundary Value Analysis": 11,
      "Decision Table Testing": 28
    },
    "by_priority": { "High": 15, "Medium": 25, "Low": 21 }
  }
}
```

---

## 4. Black-Box Technique Selection

Each coverage item carries a `type` field on which the engine selects
the appropriate black-box technique. The mapping is recorded in
Table 2 and follows ISO/IEC/IEEE 29119-4.

**Table 2.** Coverage type to technique mapping.

| Coverage type | Technique | Rationale |
|---|---|---|
| `positive` / `negative` | Equivalence Partitioning (EP) | One representative value per valid or invalid class. |
| `boundary` | Boundary Value Analysis (BVA) | Defects cluster at the edges of ranges; values are sampled on and around the limit. |
| Several items per requirement | Decision Table Testing (DT) | Independent conditions can co-fail even when each is correct in isolation. |
| `fallback` / `unknown` | Manual Review | The rule engine cannot infer; the case is flagged for human attention. |

### 4.1 Equivalence Partitioning

For each `positive` or `negative` coverage item, the engine emits one
test case. The case corresponding to the coverage item *"quantity
less than stock"* prescribes a valid quantity and asserts acceptance.

### 4.2 Boundary Value Analysis

For each `boundary` coverage item, the engine emits one test case.
The coverage engine itself generates the boundary descriptions
(`quantity = 0`, `quantity = stock`, `quantity = stock + 1`). The
expected outcome respects the constraint window where it can be
inferred and is conservative otherwise.

### 4.3 Decision Table Testing

Whenever a requirement owns several coverage items, the engine emits
one to three additional decision-table cases:

1. All required conditions satisfied — acceptance (positive
   combination).
2. Exactly one required condition violated — rejection (negative
   combination).
3. Several conditions violated — rejection (only when at least two
   negative items exist).

If no usable combination can be inferred, a single basic case is
emitted with the flag `need_manual_review = true`. The cap of three
decision-table cases per requirement bounds the suite size.

---

## 5. White-Box State Transition (FR 4.0)

[core/state_model.py](../core/state_model.py) consumes a labelled
state machine and emits test cases under one of three coverage
criteria.

**Table 3.** State-transition coverage criteria.

| Criterion | What is covered |
|---|---|
| `all_states` | Every reachable state is visited at least once. |
| `all_transitions` | Every valid edge is fired at least once. |
| `all_transitions+guards` | All valid edges plus declared invalid edges (negative guards). |

For the Order status machine defined in
[data/order_state_model.json](../data/order_state_model.json), the
three criteria produce two, two, and four test cases respectively.
The output objects share the same JSON shape as the black-box engine,
so they flow through the optimiser, exporter, and in-UI runner
without adaptation.

---

## 6. Test Case Structure

Every generated test case carries the field set recorded in Table 4.

**Table 4.** Fields of a generated test case.

| Field | Purpose |
|---|---|
| `test_case_id` | Stable, readable identifier of the form `TC-REQ-NNN-NNN`. |
| `requirement_id` / `feature` | Source requirement and capability label. |
| `title` / `description` | Human-readable summary. |
| `test_design_technique` | EP / BVA / DT / ST / Manual Review. |
| `coverage_item` / `coverage_type` | The originating coverage item. |
| `preconditions` / `test_data` / `steps` | Setup, data, and execution. |
| `expected_result` | Free-text expected outcome. |
| `oracle` | Machine-checkable expectation (FR 5.0). |
| `priority` / `risk_level` / `risk_score` | Priority derived from the risk register. |
| `traceability` | `source_requirement`, `covered_item`, `coverage_strategy`. |
| `review_status` / `need_manual_review` | Generation state. |

---

## 7. Test Data Inference

`infer_test_data` derives a small, plausible data dictionary from the
description of the coverage item. The matching is keyword-based; a
selection of rules is shown in Table 5.

**Table 5.** Selected test-data inference rules.

| Coverage text | Generated `test_data` |
|---|---|
| `username already exists` | `{"username": "existing_user"}` |
| `username is new unique value` | `{"username": "new_user_001"}` |
| `password length = 7` | `{"password": "A1bcdef"}` (length 7, mixed case, digit) |
| `missing uppercase` | `{"password": "abc12345"}` |
| `contains all required` | `{"password": "Abc12345"}` |

The rules match on lowercase substrings; verbose LLM-emitted
descriptions such as *"missing uppercase (has ['lowercase',
'digit'])"* therefore resolve correctly.

---

## 8. Expected-Result Inference

`infer_expected_result` mirrors the data inference. *Positive* cases
assert acceptance and continuation; *negative* cases assert rejection
with a meaningful error; *boundary* cases consult the constraint
window where extractable, otherwise the wording is conservative;
*fallback* and *unknown* cases require human review against the
requirement.

---

## 9. Test Oracle (FR 5.0)

[core/oracle.py](../core/oracle.py) augments the free-text
`expected_result` with a machine-checkable expectation, recorded as
the JSON object shown below.

```json
{
  "http_status_min": 400,
  "http_status_max": 400,
  "must_contain": ["stock"],
  "must_not_contain": [],
  "side_effect": {}
}
```

The selection rules are summarised in Table 6.

**Table 6.** Oracle selection rules.

| Coverage type | Default expectation |
|---|---|
| `positive` | 200–201. |
| `negative` | 400. |
| `boundary` | Inspects keyword hints (`equal to stock`, `= 0`, `exceeds`, …) to decide whether the value is inside or outside the allowed window. |

For rejected cases, salient keywords are extracted from the
requirement's `expected_behavior` and placed in `must_contain` so
that the harness can assert that the error message names the
violated rule. The `attach_oracles` function is idempotent: a tester
may hand-tune one oracle and regenerate the rest without losing the
manual override.

---

## 10. Risk Level to Priority

The mapping is one-to-one, recorded in Table 7.

**Table 7.** Risk level to priority.

| `risk_level` | `priority` |
|---|---|
| High | High |
| Medium | Medium |
| Low | Low |
| (missing) | Medium |

The mapping is applied during case generation and preserved by the
optimiser.

---

## 11. Suite Optimisation (FR 7.0)

### 11.1 Prioritisation

`prioritize_test_cases` performs a stable sort in descending order
of importance:

```
risk_level (High > Medium > Low)
  → risk_score (higher first)
    → technique (DT, ST > BVA > EP)
      → coverage type (boundary / negative > positive)
```

### 11.2 Risk-based minimisation

`minimize_test_suite(mode="risk_based")` applies the rule recorded in
Table 8.

**Table 8.** Minimisation rule.

| Risk level | Retention policy |
|---|---|
| High | Every case is retained. |
| Medium | One representative per coverage type is retained, together with every decision-table and state-transition case. |
| Low | Cases are deduplicated by coverage type, together with every decision-table and state-transition case; at least one case is always retained. |

### 11.3 Public entry point

`optimize_test_suite` optionally refreshes the risk and priority of
each case from the supplied risk JSON, then prioritises, then
minimises. It returns the structure shown below.

```json
{
  "optimized_test_cases": [ ... ],
  "optimization_summary": {
    "original_count": 65,
    "optimized_count": 61,
    "strategy": "risk_based_minimization",
    "removed_count": 4
  }
}
```

---

## 12. Validation

The engines are internally verified by the unit suite. Table 9 records
the per-module case counts.

**Table 9.** Unit-test coverage of the design engines.

| Module | Cases |
|---|---|
| `testcase_generator_test.py` | 11 — technique selection, identifier format, traceability, risk defaults, fallback, summary, empty input. |
| `optimizer_test.py` | 8 — prioritisation order, minimisation invariants, tolerant input. |
| `state_model_test.py` | 8 — model loading, all-states, all-transitions, guard generation, schema parity. |
| `oracle_test.py` | 9 — positive and negative defaults, boundary heuristics, keyword extraction, idempotence. |
| `exporter_test.py` | 11 — round-trip through CSV, JSON, Excel; serialisation of nested fields. |

All forty-seven engine unit tests pass offline.

---

## References

- ISO/IEC/IEEE 29119-4:2021, *Software and systems engineering — Software testing — Part 4: Test techniques*.
- International Software Testing Qualifications Board (ISTQB), *Foundation Level Syllabus*, 2018.
