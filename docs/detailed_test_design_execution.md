# Detailed Test Design and Execution — Order Creation Module

## Abstract

This document records the detailed test design and execution carried
out on the highest-risk module of the target application, namely the
Order Creation API of the Mini-E-Commerce backend. It follows the
seven-stage arc prescribed by the assignment — concept, coverage-item
identification, coverage strategy and method, traceability, prompt
design, result analysis, and evidence-based improvement — and reports
two real defects, of distinct origins, that were detected through the
designed suite, repaired, and re-verified. The presentation aligns
with the test-technique vocabulary of ISO/IEC/IEEE 29119-4 and the
foundation-level test process of ISTQB.

---

## 1. Concept

The Order Creation API constitutes the commercial nucleus of the
target application: every fulfilled order traverses it, and its
output mutates inventory state. The risk register
([risk_analysis_report.md](risk_analysis_report.md) §3) accordingly
classifies the requirements served by this endpoint as the
highest-impact cluster in the SUT.

A single request to `POST /api/orders/create/` must satisfy several
independent rules simultaneously. Table 1 enumerates these rules and
the requirements that prescribe them.

**Table 1.** Logical rules enforced by the Order Creation API.

| Rule | Requirement |
|---|---|
| At least one item is supplied. | REQ-007 |
| Customer name, telephone, and address are all present. | REQ-008 |
| The product identified by each item exists. | REQ-006, REQ-009 |
| The ordered quantity is greater than zero and does not exceed the available stock. | REQ-009 |
| Stock is decremented on success and remains unchanged on failure. | REQ-010 |
| `total_price = Σ price × quantity`. | REQ-006 |

Because the rules are independent yet co-acting, the module is a
natural candidate for the combined application of equivalence
partitioning, boundary value analysis, and decision-table testing.
This combination is recommended by ISO/IEC/IEEE 29119-4 for any
multi-condition transactional endpoint.

---

## 2. Coverage-Item Identification

The tool's parser (see [prompt_design.md](prompt_design.md)) renders
each natural-language requirement into the structured form defined by
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

The coverage engine
([core/coverage_analysis.py](../core/coverage_analysis.py)) then
expands the `relational` constraint into the canonical boundary trio
prescribed for the `<=` relation:

**Table 2.** Coverage items derived from REQ-009.

| Coverage item | Type |
|---|---|
| `quantity less than stock` | positive |
| `quantity equals stock` | boundary |
| `quantity greater than stock` | negative |

Across REQ-006 to REQ-010 the engine produces a layered set of
coverage items that comprise happy paths, missing-field negatives, the
quantity boundary trio, and the empty-items boundary.

The Streamlit interface presents the coverage items in an editable
table at step 4 of the workflow. The tester may add a lower-boundary
item for `quantity = 0`, delete a redundant item, or relabel the type
of an item; any such modification invalidates the downstream
artefacts, which are regenerated on the next visit. This realises the
interactive-review capability mandated by the assignment.

---

## 3. Coverage Strategy and Method

Each coverage type is paired with a test design technique by the rule
specified in [test_design.md](test_design.md) §3. Table 3 records the
application of this rule to the present module.

**Table 3.** Coverage type, technique, and method on the Order Creation
module.

| Coverage type | Technique | Method |
|---|---|---|
| positive | Equivalence Partitioning | One valid order is submitted; acceptance with status 201 is asserted. |
| negative | Equivalence Partitioning | One invalid order is submitted; rejection with status 400 is asserted. |
| boundary | Boundary Value Analysis | `quantity` is sampled on and around the limits. |
| Multiple co-acting conditions | Decision Table Testing | Combinations of the create rules are exercised: all satisfied (acceptance), one violated (rejection), several violated (rejection). |

For the order-creation cluster the rule-pipeline baseline produces
twenty-five test cases distributed across the techniques as shown in
Table 4.

**Table 4.** Test cases produced for REQ-006 – REQ-010.

| Technique | Cases |
|---|---:|
| Equivalence Partitioning | 10 |
| Boundary Value Analysis | 5 |
| Decision Table Testing | 10 |
| **Total** | **25** |

Because all five requirements are classified High or Medium risk, the
risk-based minimisation of the optimiser retains the full set; see
[coverage_strategy.md](coverage_strategy.md) §5 for the minimisation
rule.

---

## 4. Traceability

Every generated test case carries a `traceability` block recording the
source requirement, the covered item, and the coverage strategy. The
chain *requirement → coverage item → test case → executing function*
is therefore fully reconstructable. The project-wide matrix is
regenerated automatically by
[scripts/build_traceability.py](../scripts/build_traceability.py) into
[traceability_matrix.md](traceability_matrix.md). Table 5 reproduces
the slice for the quantity boundary as an illustration.

**Table 5.** Traceability slice for REQ-009.

| Requirement | Coverage item | Technique | Generated case | Hand-written test |
|---|---|---|---|---|
| REQ-009 | quantity less than stock | EP | TC-REQ-009-001 (positive) | `test_req009_quantity_equal_to_stock_is_accepted` |
| REQ-009 | quantity equals stock | BVA | TC-REQ-009-003 (boundary) | `test_req009_quantity_equal_to_stock_is_accepted` |
| REQ-009 | quantity greater than stock | EP / DT | TC-REQ-009-002 (negative) | `test_req009_quantity_one_above_stock_returns_400` |
| REQ-009 | quantity = 0 (lower bound) | BVA | added at step 4 of the workflow | `test_req009_quantity_zero_returns_400` |

The final row is the lower-boundary case prescribed by boundary value
analysis. Its outcome is reported in §6 and constitutes the evidence
underpinning Defect 1 in §7.

---

## 5. Prompt Design

Two stages of the pipeline are realised by a large language model:
requirement parsing and risk analysis. Both prompts are engineered for
strict, deterministic, schema-compliant JSON. The complete rationale
appears in [prompt_design.md](prompt_design.md); two consequences are
salient for the present module:

1. The parser prompt maps the phrase *"shall not exceed available
   stock"* onto a `relational` constraint with operator `<=`, which is
   exactly the constraint type that drives the boundary trio of §2.
2. The risk prompt's four-dimension scoring places REQ-006 and REQ-010
   in the High band, with the consequence that the present module
   receives the deepest coverage.

A live invocation of the parser on REQ-009 reproduces the
`relational` constraint verbatim, confirming that the prompt and the
downstream engine agree on the schema.

---

## 6. Result Analysis

The tester exports the suite at step 7 of the workflow and executes
it against the running backend, either through step 8 of the user
interface or directly with PyTest from the command line. The complete
execution record is documented in
[test_result_analysis.md](test_result_analysis.md). Table 6
summarises the outcome of the first execution; Table 7 records the
explicit mapping from designed test case to coverage item and
coverage strategy that the assignment specifies.

**Table 6.** Outcome of the first execution.

| Design intent | Coverage item | Outcome |
|---|---|---|
| Valid order accepted | quantity less than stock (positive) | Pass |
| Upper boundary accepted | quantity equals stock (boundary) | Pass |
| Over-stock rejected | quantity greater than stock (negative) | Pass |
| Missing customer field rejected | missing name / phone / address | Pass |
| Non-existent product rejected | non-existing product id | Pass |
| Lower boundary rejected | **quantity = 0 (boundary)** | **Fail — 201 instead of 400** |
| Stock rollback on partial failure | first item valid, second item missing | **Fail — stock decremented to 3 instead of remaining at 5** |

**Table 7.** Designed test case ↔ coverage item ↔ strategy mapping.

| Test case | Coverage item (identified) | Strategy and method | Technique | Result |
|---|---|---|---|---|
| Valid single-item order | order with all required fields present | positive path coverage | EP | Pass |
| Multi-item `total_price` | Σ price × quantity | positive plus state verification | EP / white-box invariant | Pass |
| Empty items | items length = 0 | boundary value coverage | BVA | Pass |
| Missing customer name / phone / address | each required field absent | decision-table / negative | DT | Pass |
| Non-existent product | product id absent | negative path coverage | EP | Pass |
| Quantity equals stock | upper boundary, inclusive | boundary value coverage | BVA | Pass |
| Quantity = stock + 1 | upper boundary, exclusive | boundary value coverage | BVA | Pass |
| **Quantity = 0** | **lower boundary, invalid** | **boundary value coverage** | **BVA** | **Fail → repaired (§7)** |
| Stock decremented after success | stock decreases by ordered quantity | state verification | white-box invariant | Pass |
| Rejected order leaves stock untouched | stock unchanged on 4xx | state verification | white-box invariant | Pass |
| **Multi-item partial failure** | **first item commits, second fails** | **decision-table / cross-condition invariant** | **DT** | **Fail → repaired (§7)** |

Each executed outcome is anchored to a deliberately identified
coverage item and a named technique; no test exists by accident, and
every identified coverage item is realised by at least one executable
case.

---

## 7. Evidence-Based Improvement

Two real defects were detected by the present suite. They are of
distinct origins, repaired by distinct interventions, and re-verified
under the same harness.

### 7.1 Defect 1 — non-positive quantity accepted

The boundary value analysis of `quantity` (Table 2) prescribed
`quantity = 0` as an invalid lower-boundary value. The corresponding
test case
([`tests/integration/test_order_api.py`](../tests/integration/test_order_api.py)::`test_req009_quantity_zero_returns_400`)
returned HTTP 400 in expectation but received HTTP 201 from the SUT,
indicating that the lower bound was unguarded.

The view was amended to reject any non-positive quantity prior to the
stock check:

```python
if quantity <= 0:
    transaction.set_rollback(True)
    return Response(
        {"error": "Quantity must be greater than 0"},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

Re-execution of the suite confirms that the test now passes and that
no other test regresses.

### 7.2 Defect 2 — stock leak under multi-item partial failure

A decision-table case combined two independent conditions of the
order rule: *first item valid* and *second item's product absent*.
The corresponding test
(`test_req010_multi_item_partial_failure_rolls_back_all_stock`)
returned HTTP 400 as expected, but the stock of the first item had
been silently decremented from five to three. The view processed
items sequentially and persisted each stock change immediately, so a
later failure left earlier deductions committed.

The handler was wrapped in a database transaction so that either every
mutation commits or none does:

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

The decorator opens an atomic block; a call to
`transaction.set_rollback(True)` immediately before any 4xx return
discards the entire block, including stock decrements applied to
earlier items. Re-execution confirms that the test passes and that
the full hand-written backend suite passes without regression.

### 7.3 Discussion

Two observations are pertinent to the assignment's emphasis on
evidence-based improvement:

1. **Different techniques expose different defects.** The boundary
   value technique revealed a missing single-condition guard; the
   decision-table technique revealed a missing cross-condition
   invariant. A suite that used only one of the two would have left
   the other class of defect undetected. This is the empirical
   justification for the multi-technique strategy adopted in §3.
2. **Traceability localises every repair.** Each failing test traced
   directly to one requirement and one coverage item; the
   corresponding repair was a single guard or a single decorator
   rather than a broad rewrite. Localised, evidence-anchored repair
   is a desirable property of risk-based, technique-driven testing.

---

## 8. Designer Involvement

The assignment requires that the tool support interactive review at
every stage. In the present module the tester:

1. revised the wording of REQ-009 at step 2 to sharpen the
   constraint;
2. revised the coverage items at step 4 to add the
   `quantity = 0` lower-boundary item that the parser had omitted;
3. reviewed and trimmed the generated test cases at step 5;
4. executed the suite from step 8 and observed the failures of §7;
5. amended the backend and re-ran the suite, observing the green
   result.

Each modification invalidated the cached downstream artefacts, so the
pipeline always reflected the tester's latest decisions. This
concretely realises the human-in-the-loop, evidence-driven test
design process called for in the assignment.

---

## References

- ISO/IEC/IEEE 29119-4:2021, *Software and systems engineering — Software testing — Part 4: Test techniques*.
- ISO/IEC/IEEE 29119-2:2021, *Part 2: Test processes*.
- International Software Testing Qualifications Board (ISTQB), *Foundation Level Syllabus*, 2018.
