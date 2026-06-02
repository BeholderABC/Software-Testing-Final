# Detailed Test Design and Execution — Order Creation Module

> **Subject module:** the Order Creation API (`POST /api/orders/create/`) of
> the Django REST Mini-E-Commerce backend — the highest-risk module per the
> [risk analysis report](risk_analysis_report.md).
> **Relationship to the tool:** this hand-authored document is the gold
> reference; AutoTestDesign emits an equivalent document per run into
> `outputs/run_<timestamp>/docs/detailed_test_design_execution.md`, with the
> per-mode result table and generation metrics filled from that run.

## Abstract

This document records the detailed test design and execution carried out on
the highest-risk module of the target application. It follows the
assignment's seven-stage arc — concept, coverage-item identification,
coverage strategy and method, traceability, prompt design, result analysis,
and evidence-based improvement — placed inside the IEEE 829 design/case/
summary frame. Two real defects, of distinct origins, were detected through
the designed suite, repaired, and re-verified. The presentation aligns with
the test-technique vocabulary of ISO/IEC/IEEE 29119-4 and the ISTQB
foundation-level test process. A map from sections to the assessment
criteria is given in Appendix A.

---

## 1. Design specification identifier

| Field | Value |
|---|---|
| Specification | Detailed Test Design & Execution — Order Creation |
| Version | 2.0 (IEEE 829-2008 aligned) |
| Module under test | `POST /api/orders/create/` |
| Requirements | REQ-006 – REQ-010 |
| Risk | Highest-risk cluster ([risk_analysis_report.md](risk_analysis_report.md) §6) |
| Related | [test_plan.md](test_plan.md), [coverage_strategy.md](coverage_strategy.md), [prompt_design.md](prompt_design.md), [traceability_matrix.md](traceability_matrix.md), [test_result_analysis.md](test_result_analysis.md) |

---

## 2. Concept and features to be tested

The Order Creation API is the commercial nucleus of the target application:
every fulfilled order traverses it, and its output mutates inventory state.
The risk register ([risk_analysis_report.md](risk_analysis_report.md) §4)
classifies the requirements it serves as the highest-impact cluster.

A single request to `POST /api/orders/create/` must satisfy several
independent rules simultaneously. Table 1 enumerates them and the
requirements that prescribe them.

**Table 1.** Logical rules enforced by the Order Creation API.

| Rule | Requirement |
|---|---|
| At least one item is supplied. | REQ-007 |
| Customer name, telephone, and address are all present. | REQ-008 |
| The product identified by each item exists. | REQ-006, REQ-009 |
| The ordered quantity is > 0 and does not exceed available stock. | REQ-009 |
| Stock is decremented on success and unchanged on failure. | REQ-010 |
| `total_price = Σ price × quantity`. | REQ-006 |

Because the rules are independent yet co-acting, the module is a natural
candidate for the combined application of equivalence partitioning, boundary
value analysis, and decision-table testing (black box), reinforced by a
white-box state/invariant check on the stock mutation. This combination is
recommended by ISO/IEC/IEEE 29119-4 for any multi-condition transactional
endpoint.

---

## 3. Coverage-item identification

The tool's parser ([prompt_design.md](prompt_design.md)) renders each
natural-language requirement into the structured form of
[constraint_schema.md](constraint_schema.md). For REQ-009 the parser
produces:

```jsonc
{
  "requirement_id": "REQ-009",
  "feature": "Reject order whose quantity exceeds stock",
  "constraints": [
    { "field": "quantity", "type": "relational",
      "operator": "<=", "target": "stock" }
  ]
}
```

The coverage engine ([core/coverage_analysis.py](../core/coverage_analysis.py))
expands the `relational` constraint into the canonical boundary trio for the
`<=` relation:

**Table 2.** Coverage items derived from REQ-009.

| Coverage item | Type |
|---|---|
| `quantity less than stock` | positive |
| `quantity equals stock` | boundary |
| `quantity greater than stock` | negative |

Across REQ-006 – REQ-010 the engine produces a layered set comprising happy
paths, missing-field negatives, the quantity boundary trio, and the
empty-items boundary. The Streamlit interface presents these in an editable
table at Step 4: the tester may add a lower-boundary item for
`quantity = 0`, delete a redundant item, or relabel a type; any change
invalidates downstream artefacts, which regenerate. This realises the
interactive-review capability mandated by the assignment.

---

## 4. Coverage strategy and method

Each coverage type is paired with a test-design technique by the rule in
[test_design.md](test_design.md) §3.

**Table 3.** Coverage type → technique → method (Order Creation module).

| Coverage type | Technique | Method |
|---|---|---|
| positive | Equivalence Partitioning | One valid order is submitted; acceptance with 201 is asserted. |
| negative | Equivalence Partitioning | One invalid order is submitted; rejection with 400 is asserted. |
| boundary | Boundary Value Analysis | `quantity` is sampled on and around the limits (0, stock, stock+1). |
| combination | Decision Table Testing | Combinations of the create rules: all satisfied (accept), one violated (reject), several violated (reject). |
| state / invariant | State-verification (white box) | Stock decremented by exactly the ordered quantity on success; unchanged on a 4xx. |

For the order-creation cluster the rule-pipeline baseline produces 25 test
cases distributed as in Table 4.

**Table 4.** Test cases produced for REQ-006 – REQ-010.

| Technique | Cases |
|---|---:|
| Equivalence Partitioning | 10 |
| Boundary Value Analysis | 5 |
| Decision Table Testing | 10 |
| **Total** | **25** |

Because all five requirements are High or Medium risk, the risk-based
minimisation retains the full set ([coverage_strategy.md](coverage_strategy.md) §5).

---

## 5. Test case specification and coverage

Each generated case carries `test_case_id`, `requirement_id`,
`test_design_technique`, `coverage_type`, structured `test_data`, ordered
`steps`, a synthesised `oracle` (expected status + assertions), `priority`,
and a `traceability` block. Table 5 specifies the representative cases for
the module and the coverage item each realises.

**Table 5.** Designed test case ↔ coverage item ↔ strategy mapping.

| Test case | Coverage item (identified) | Strategy / method | Technique | Box |
|---|---|---|---|---|
| Valid single-item order | order with all required fields present | positive path coverage | EP | black |
| Multi-item `total_price` | Σ price × quantity | positive + state verification | EP / invariant | black + white |
| Empty items | items length = 0 | boundary value coverage | BVA | black |
| Missing customer name / phone / address | each required field absent | decision-table / negative | DT | black |
| Non-existent product | product id absent | negative path coverage | EP | black |
| Quantity equals stock | upper boundary, inclusive | boundary value coverage | BVA | black |
| Quantity = stock + 1 | upper boundary, exclusive | boundary value coverage | BVA | black |
| **Quantity = 0** | **lower boundary, invalid** | **boundary value coverage** | **BVA** | black |
| Stock decremented after success | stock decreases by ordered quantity | state verification | invariant | white |
| Rejected order leaves stock untouched | stock unchanged on 4xx | state verification | invariant | white |
| **Multi-item partial failure** | **first item commits, second fails** | **decision-table / cross-condition invariant** | **DT** | black + white |

Every identified coverage item is realised by at least one executable case,
and no case exists without an identified coverage item — the
**coverage-explanation** the assignment requires. The black-box techniques
(EP, BVA, DT) and the white-box state/invariant checks are both exercised on
this module, satisfying the "multiple black-box techniques and also
white-box techniques" requirement.

---

## 6. Prompt design and traceability

### 6.1 Prompt design

Two pipeline stages are realised by a language model: requirement parsing
and risk analysis. Both prompts are engineered for strict, deterministic,
schema-compliant JSON ([prompt_design.md](prompt_design.md)). Two
consequences are salient here:

1. The parser prompt maps *"shall not exceed available stock"* onto a
   `relational` constraint with operator `<=`, which is exactly the
   constraint type that drives the boundary trio of §3.
2. The risk prompt's four-dimension scoring places REQ-006 and REQ-010 in
   the High band, so this module receives the deepest coverage.

A live invocation of the parser on REQ-009 reproduces the `relational`
constraint verbatim, confirming prompt and downstream engine agree on the
schema. The same prompt/data discipline governs the **document** generation
(`prompts/detailed_design_prompt.txt`): the report you are reading is itself
reproducible from the run's JSON.

### 6.2 Traceability

Every case keeps a `traceability` block recording the source requirement,
the covered item, and the strategy, so the chain *requirement → coverage
item → test case → executing function* is fully reconstructable. The
project-wide matrix regenerates via
[scripts/build_traceability.py](../scripts/build_traceability.py) into
[traceability_matrix.md](traceability_matrix.md). Table 6 reproduces the
REQ-009 slice.

**Table 6.** Traceability slice for REQ-009.

| Requirement | Coverage item | Technique | Generated case | Hand-written test |
|---|---|---|---|---|
| REQ-009 | quantity less than stock | EP | TC-REQ-009-001 (positive) | `test_req009_quantity_equal_to_stock_is_accepted` |
| REQ-009 | quantity equals stock | BVA | TC-REQ-009-003 (boundary) | `test_req009_quantity_equal_to_stock_is_accepted` |
| REQ-009 | quantity greater than stock | EP / DT | TC-REQ-009-002 (negative) | `test_req009_quantity_one_above_stock_returns_400` |
| REQ-009 | quantity = 0 (lower bound) | BVA | added at Step 4 of the workflow | `test_req009_quantity_zero_returns_400` |

The final row is the lower-boundary case prescribed by BVA; its outcome
(§7) underpins Defect 1 (§8).

---

## 7. Result analysis (Test Summary Report)

The suite is exported at Step 7 and executed against the running backend at
Step 8 (or directly with PyTest). The complete record is in
[test_result_analysis.md](test_result_analysis.md). The tool can execute the
suite in up to four modes — source ∈ {generated, optimised} × HTTP execution
∈ {representative-per-key (default), full-individual (diagnostic)} — and the
generated report tabulates each mode it was run in, confirming the
deduplicated and full executions reach the same verdict. Table 7 summarises
the outcome of the first (defect-revealing) execution.

**Table 7.** Outcome of the first execution.

| Design intent | Coverage item | Outcome |
|---|---|---|
| Valid order accepted | quantity less than stock (positive) | Pass |
| Upper boundary accepted | quantity equals stock (boundary) | Pass |
| Over-stock rejected | quantity greater than stock (negative) | Pass |
| Missing customer field rejected | missing name / phone / address | Pass |
| Non-existent product rejected | non-existing product id | Pass |
| Lower boundary rejected | **quantity = 0 (boundary)** | **Fail — 201 instead of 400** |
| Stock rollback on partial failure | first item valid, second item missing | **Fail — stock decremented to 3 instead of remaining at 5** |

Each executed outcome is anchored to a deliberately identified coverage item
and a named technique; no test exists by accident, and every identified
coverage item is realised by at least one executable case.

---

## 8. Evidence-based improvement

Two real defects were detected by the present suite. They are of distinct
origins, repaired by distinct interventions, and re-verified under the same
harness.

### 8.1 Defect 1 — non-positive quantity accepted

The BVA of `quantity` (Table 2) prescribed `quantity = 0` as an invalid
lower-boundary value. The corresponding test
([`tests/integration/test_order_api.py`](../tests/integration/test_order_api.py)::`test_req009_quantity_zero_returns_400`)
expected HTTP 400 but received HTTP 201, indicating an unguarded lower
bound. The view was amended to reject any non-positive quantity before the
stock check:

```python
if quantity <= 0:
    transaction.set_rollback(True)
    return Response(
        {"error": "Quantity must be greater than 0"},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

Re-execution confirms the test now passes with no regression.

### 8.2 Defect 2 — stock leak under multi-item partial failure

A decision-table case combined two conditions — *first item valid* and
*second item's product absent*. The test
(`test_req010_multi_item_partial_failure_rolls_back_all_stock`) returned
HTTP 400 as expected, but the first item's stock had been silently
decremented from five to three: the view processed items sequentially and
persisted each change immediately, so a later failure left earlier
deductions committed. The handler was wrapped in a database transaction:

```python
from django.db import transaction
# ...
class CreateOrderAPIView(APIView):
    @transaction.atomic
    def post(self, request):
        # ...
        # every early-return path now signals rollback:
        transaction.set_rollback(True)
        return Response({"error": "..."}, status=400)
```

The decorator opens an atomic block; `set_rollback(True)` before any 4xx
return discards the entire block, including earlier stock decrements.
Re-execution confirms the test passes and the full hand-written backend
suite passes without regression.

### 8.3 Discussion

1. **Different techniques expose different defects.** BVA revealed a missing
   single-condition guard; the decision-table technique revealed a missing
   cross-condition invariant. A suite using only one would have left the
   other class undetected — the empirical justification for the
   multi-technique strategy of §4.
2. **Traceability localises every repair.** Each failing test traced to one
   requirement and one coverage item; the corresponding repair was a single
   guard or decorator, not a broad rewrite.

A third defect, in the order-status state machine (REQ-012), is detected by
the white-box state-transition technique and documented in
[risk_analysis_report.md](risk_analysis_report.md) §9 and
[test_result_analysis.md](test_result_analysis.md); it lies outside the
Order Creation module that is the subject of this document.

---

## 9. Designer involvement (interactive review)

The assignment requires the tool to support interactive review at every
stage. For this module the tester:

1. revised the wording of REQ-009 at Step 2 to sharpen the constraint;
2. added the `quantity = 0` lower-boundary coverage item at Step 4 that the
   parser had omitted;
3. reviewed and trimmed the generated cases at Step 5;
4. executed the suite from Step 8 and observed the failures of §7;
5. amended the backend and re-ran the suite, observing the green result.

Each modification invalidated the cached downstream artefacts, so the
pipeline always reflected the tester's latest decisions — concretely
realising the human-in-the-loop, evidence-driven process the assignment
calls for.

---

## References

- IEEE 829-2008, *IEEE Standard for Software and System Test Documentation*.
- ISO/IEC/IEEE 29119-4:2021, *Software testing — Part 4: Test techniques*.
- ISO/IEC/IEEE 29119-2:2021, *Part 2: Test processes*.
- International Software Testing Qualifications Board (ISTQB), *Foundation Level Syllabus*, 2018.
