# Test Result Analysis — Mini-E-Commerce Backend

## Abstract

This document reports the analysis of executing, against the target
application, the test suite designed by AutoTestDesign. It records
the overall execution outcome, the three defects that the designed
suite detected, the repairs applied, and the regression results.
Each defect was found by a distinct test design technique — boundary
value analysis, decision-table / invariant analysis, and white-box
state-transition testing — so the three together evidence the payoff
of the multi-technique strategy. The presentation follows the
*find-fix-verify* closure required by the assignment's evidence-based-
improvement criterion and aligns with the test-process vocabulary of
ISO/IEC/IEEE 29119-2.

---

## 1. Scope

### 1.1 Target application

The system under test is the Django REST Mini-E-Commerce backend,
identified as the target application throughout the project
documentation. The focus module is the Order Creation endpoint
(`POST /api/orders/create/`), which the risk register classifies as
the highest-risk locus of the application
([risk_analysis_report.md](risk_analysis_report.md) §3). All twelve
catalogued requirements (REQ-001 – REQ-012) are exercised by the
suite.

### 1.2 Execution layering

Execution is organised in three levels in accordance with the ISTQB
foundation-level taxonomy. The level definitions and their physical
locations are recorded in Table 1.

**Table 1.** Test levels and their location.

| Level | Object of verification | Location |
|---|---|---|
| Unit | The internal engines of the tool | `tests/unit/` (48 cases) |
| Integration (data-driven) | Tool-produced artefacts executed against the backend | `tests/integration/test_data_driven_orders.py` (51 + 1 sanity) |
| System (hand-written) | End-to-end backend behaviour | `tests/integration/test_mini_ecommerce_api.py`, `test_order_api.py`, `test_order_status_api.py` (30 cases) |

The data-driven level includes the white-box state-transition cases
(`TC-REQ-012-S001 … S004`) generated from the Order status machine
(FR 4.0): each is executed against the backend as a multi-step PATCH
sequence rather than a single request, so the state machine's guards
are genuinely exercised.

---

## 2. Execution Summary

The aggregate outcome of running the suite under two configurations
is recorded in Table 2.

**Table 2.** Aggregate execution outcome.

| Configuration | Outcome |
|---|---|
| Offline (target not running) | 48 passed, 81 skipped — the backend-dependent suites perform a graceful skip rather than a failure. |
| Backend running | 129 passed (excluding the two LLM-only smoke tests). |

Two LLM smoke tests under `tests/unit/parser_test.py` and
`tests/unit/risk_test.py` require live API access and are executed
separately.

The present aggregate is fully green. The substantive narrative of
this document, however, concerns the *first* execution against the
order-creation and order-status modules, which uncovered three
defects of distinct origins.

---

## 3. Defect 1 — Detected by Boundary Value Analysis

### 3.1 Hypothesis

The order quantity rule (REQ-009) was analysed using boundary value
analysis (ISO/IEC/IEEE 29119-4 §6.2). The `quantity` field admits
the boundary class shown in Table 3.

**Table 3.** Boundary class of `quantity`.

| Value | Class | Expected outcome |
|---|---|---|
| 0 | invalid lower boundary | reject with HTTP 400 |
| 1 | valid minimum | accept |
| `stock` | valid upper boundary | accept |
| `stock + 1` | invalid upper boundary | reject with HTTP 400 |

### 3.2 Observation

The tool generated the lower-boundary case
(`test_req009_quantity_zero_returns_400` in
[tests/integration/test_order_api.py](../tests/integration/test_order_api.py)).
Its first execution returned the result recorded in Table 4.

**Table 4.** First-execution result of Defect 1.

| | |
|---|---|
| Expected | HTTP 400 Bad Request |
| Observed | HTTP 201 Created |

The backend correctly rejected *insufficient stock*
(`quantity > stock`) but did not validate the lower bound, so an
order item with `quantity = 0` was accepted. The defect belongs to
the class of single-condition validation omissions characteristic of
ad-hoc happy-path testing — and characteristic of the class of defect
that boundary value analysis is designed to catch.

### 3.3 Repair

A guard was added to the order-creation view in
[target_app/.../store/views.py](../target_app/Mini-E-Commerce-System/Backend/store/views.py),
rejecting any non-positive quantity prior to the stock check:

```python
if quantity <= 0:
    transaction.set_rollback(True)
    return Response(
        {"error": "Quantity must be greater than 0"},
        status=status.HTTP_400_BAD_REQUEST,
    )
```

The guard now occupies line 102 of `views.py`.

### 3.4 Re-test

After the repair, the order suite was re-executed against the
backend. The pertinent results are recorded in Table 5.

**Table 5.** Re-test results for Defect 1.

| Test case | Outcome |
|---|---|
| `test_req009_quantity_zero_returns_400` | Pass — HTTP 400 returned |
| `test_req009_quantity_one_above_stock_returns_400` | Pass |
| `test_req009_quantity_equal_to_stock_is_accepted` | Pass |

The boundary that exposed the defect is now permanently guarded by
the regression test, so the repair cannot silently regress.

---

## 4. Defect 2 — Detected by Decision-Table / Invariant Analysis

### 4.1 Hypothesis

Boundary analysis exposed a missing input check. A different
technique was expected to reveal a different class of defect in the
same module: the *atomicity of a multi-item order*. The decision
table for REQ-006 together with REQ-010 contains a row that combines
two conditions across items — *first item valid*, *second item's
product missing* — which raises a state-invariant question: when the
second item fails, what becomes of the stock the first item already
consumed?

### 4.2 Observation

The combination case was made executable as
`test_req010_multi_item_partial_failure_rolls_back_all_stock`
([tests/integration/test_order_api.py](../tests/integration/test_order_api.py)).
Its first execution returned the result recorded in Table 6.

**Table 6.** First-execution result of Defect 2.

| | |
|---|---|
| Expected | Stock of the first item unchanged after rejection |
| Observed | Stock decreased from 5 to 3; the failed order silently leaked stock |

The view processed items sequentially and persisted each stock change
immediately; a later failure left earlier mutations committed. This
is a classic atomicity defect that single-condition tests do not
detect, since the failure manifests only across combined conditions.

### 4.3 Repair

The order-creation handler was wrapped in a database transaction so
that either every mutation commits or none does:

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
discards the entire block, including the stock decrements that ran
for earlier items. The repair lives in
[store/views.py](../target_app/Mini-E-Commerce-System/Backend/store/views.py)
at line 41 (the `@transaction.atomic` decorator).

### 4.4 Re-test

After the repair, the regression case passes (stock restored to 5 on
rejection); every other order test continues to pass; the full
hand-written backend suite reports 78 passing tests with no failure.

---

## 5. Defect 3 — Detected by White-Box State-Transition Testing

### 5.1 Hypothesis

The order status rule (REQ-012) was analysed as a finite state
machine (ISO/IEC/IEEE 29119-4 §7). The machine, defined in
[data/order_state_model.json](../data/order_state_model.json), holds
that `completed` and `cancelled` are terminal: no transition may
leave either. The two declared invalid edges are recorded in Table 7.

**Table 7.** Invalid (guard) edges of the Order status machine.

| Edge | Class | Expected outcome |
|---|---|---|
| `completed --cancel--> cancelled` | invalid guard | reject; remain `completed` |
| `cancelled --complete--> completed` | invalid guard | reject; remain `cancelled` |

### 5.2 Observation

The `all_transitions+guards` criterion generated the two guard cases
`TC-REQ-012-S003` and `TC-REQ-012-S004`. Each is executed as a
multi-step PATCH sequence by the data-driven harness: the prefix
drives a fresh order to the terminal state, then the final step
attempts the forbidden transition. The first execution returned the
result recorded in Table 8.

**Table 8.** First-execution result of Defect 3.

| | |
|---|---|
| Expected | HTTP 4xx; the order remains in its terminal state |
| Observed | HTTP 200; the terminal order silently transitioned |

The order detail endpoint was a default
`RetrieveUpdateDestroyAPIView` whose serialiser treated `status` as
an ordinary choice field. Any value in `STATUS_CHOICES` was therefore
accepted regardless of the current state, so a `completed` order
could be moved back to `cancelled` (and vice versa). This is a class
of defect that black-box value testing cannot reach: the status value
*itself* is legal; only the *transition* between states is illegal.

### 5.3 Repair

A transition guard was added to the order detail view in
[target_app/.../store/views.py](../target_app/Mini-E-Commerce-System/Backend/store/views.py),
rejecting any attempt to change the status of an order that already
occupies a terminal state:

```python
class OrderDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    TERMINAL_STATES = ("completed", "cancelled")

    def update(self, request, *args, **kwargs):
        order = self.get_object()
        new_status = request.data.get("status")
        if (new_status is not None
                and order.status in self.TERMINAL_STATES
                and new_status != order.status):
            return Response(
                {"status": (
                    f"order is already '{order.status}' (a terminal state) "
                    f"and cannot transition to '{new_status}'")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().update(request, *args, **kwargs)
```

The guard occupies the `update` override of `OrderDetailAPIView` in
`views.py`.

### 5.4 Re-test

After the repair, the four state-transition cases were re-executed
against the backend. The results are recorded in Table 9.

**Table 9.** Re-test results for Defect 3.

| Test case | Sequence | Outcome |
|---|---|---|
| `TC-REQ-012-S001` | `complete` | Pass — `pending → completed` accepted (200) |
| `TC-REQ-012-S002` | `cancel` | Pass — `pending → cancelled` accepted (200) |
| `TC-REQ-012-S003` | `complete, cancel` | Pass — terminal `cancel` rejected (400) |
| `TC-REQ-012-S004` | `cancel, complete` | Pass — terminal `complete` rejected (400) |

The repair was confirmed by mutation: neutralising the guard
(emptying `TERMINAL_STATES`) re-fails `S003` and `S004`, which
demonstrates that the two cases genuinely exercise the guard rather
than passing vacuously.

---

## 6. Analysis

Three real defects, of distinct origins, were detected in the
order-handling modules by three distinct techniques. The contrast is
summarised in Table 10.

**Table 10.** Contrast between the three defects.

| Attribute | Defect 1 | Defect 2 | Defect 3 |
|---|---|---|---|
| Technique applied | Boundary Value Analysis | Decision Table / cross-condition invariant | State-Transition Testing (white box) |
| Class of defect | Missing input guard | Missing transactional atomicity | Missing state-transition guard |
| Trigger | Single item with `quantity = 0` | Two items, the second of which fails after the first commits stock | A terminal order receiving a further status change |
| Symptom | HTTP 201 returned where 400 was expected | HTTP 400 returned, but stock silently leaked | HTTP 200 returned where the transition should have been rejected |
| Why ad-hoc testing fails to find it | The required boundary value is not naturally written by intuition | The defect manifests only across combined conditions | The status value is legal in isolation; only the transition is illegal |

Four observations follow.

1. **Distinct techniques expose distinct defects.** Boundary value
   analysis catches missing single-condition guards (Defect 1);
   decision-table and invariant analysis catch cross-condition state
   defects (Defect 2); state-transition testing catches illegal
   transitions between otherwise legal states (Defect 3). A suite
   that applied only a subset of the techniques would have left the
   remaining classes of defect undetected. The three-defect result is
   the expected payoff of the multi-technique strategy adopted in
   [test_plan.md](test_plan.md) §5.
2. **White-box modelling reaches where black-box testing cannot.**
   Defect 3 is invisible to value-level testing because every status
   value is individually valid; only an explicit model of the
   permitted transitions reveals the missing guard. This is the
   precise justification for the FR 4.0 white-box requirement.
3. **Systematic design exceeds the reach of ad-hoc testing.** None of
   *order zero items*, *second item fails after the first commits
   stock*, or *cancel an already-completed order* is naturally
   written by intuition; each arises as a deliberate prescription of
   a technique and is the precise input at which a defect was
   detected.
4. **Traceability supports targeted repair.** Each failing case
   traces directly to a specific requirement (REQ-009 for Defect 1;
   REQ-006 together with REQ-010 for Defect 2; REQ-012 for Defect 3)
   and to a specific coverage item; all three repairs were small (one
   guard, one decorator, and one transition check) rather than broad
   rewrites. The interactive-review loop closes the find-fix-verify
   cycle: the tester reviewed the generated cases, executed them,
   observed the failures, repaired the backend, and re-executed —
   entirely evidence-based and reproducible under the same harness.

---

## 7. Conclusion

The risk-based, multi-technique suite produced executable tests that
detected, localised, and verified the repair of three distinct
classes of real defect in the highest-risk modules of the target
application — a missing input guard, a missing transactional
atomicity, and a missing state-transition guard — each found by a
different technique. The aggregate suite is currently fully green,
with 48 offline tests passing (81 skipped without a backend) and 129
tests passing with the backend running. The exit criteria of the
test plan are therefore satisfied at the time of writing.

---

## References

- ISO/IEC/IEEE 29119-2:2021, *Software and systems engineering — Software testing — Part 2: Test processes*.
- ISO/IEC/IEEE 29119-4:2021, *Part 4: Test techniques*.
- International Software Testing Qualifications Board (ISTQB), *Foundation Level Syllabus*, 2018.
