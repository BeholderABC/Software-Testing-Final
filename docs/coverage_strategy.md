# Coverage Strategy

## Abstract

This document records the coverage strategy adopted by AutoTestDesign:
the principles that govern *what* is covered, *how* it is covered,
and *to what depth* it is covered. The strategy aligns with the
risk-based testing principle of ISO/IEC/IEEE 29119-1: test effort is
allocated in proportion to product risk. The application of the
strategy to the Mini-E-Commerce backend is summarised by the
metrics recorded in §5.

---

## 1. Introduction

A coverage strategy is the bridge between the catalogue of
identified scenarios and the executable test suite that exercises
them. Three questions are addressed below.

1. **What is covered?** Every coverage item identified by the
   coverage engine must be realised by at least one test case
   ([§2](#2-coverage-objective-traceability)).
2. **How is it covered?** Each coverage type is paired with the
   technique recommended by ISO/IEC/IEEE 29119-4
   ([§3](#3-coverage-type-to-technique-mapping)).
3. **To what depth?** The depth of coverage allocated to each
   requirement is determined by its risk level
   ([§4](#4-risk-based-coverage-depth)).

---

## 2. Coverage Objective: Traceability

The strategy enforces an end-to-end chain
*requirement → coverage item → test case → traceability block*. Every
test case carries a `traceability` block recording the originating
requirement, the covered item, and the strategy applied. A report
may therefore decompose the suite by strategy at need, and any
failure may be traced back to the rule it violates. The illustrative
chain is shown in Figure 1.

```
REQ-009 ──▶ coverage item "quantity > stock"
                       │
                       ▼
                TC-REQ-009-003
                traceability = {
                  source_requirement: "REQ-009",
                  covered_item: "quantity greater than stock",
                  coverage_strategy: "negative path coverage"
                }
```

*Figure 1.* Traceability block produced by the engine.

---

## 3. Coverage Type to Technique Mapping

The pairing of coverage type with technique follows
ISO/IEC/IEEE 29119-4 §6 and §7. Table 1 records the mapping.

**Table 1.** Coverage type to technique.

| Coverage type | Technique | Rationale |
|---|---|---|
| `positive` | Equivalence Partitioning (EP) | One representative confirms acceptance of the happy path. |
| `negative` | Equivalence Partitioning (EP) | One representative confirms rejection of an invalid input. |
| `boundary` | Boundary Value Analysis (BVA) | Defects cluster at the edges of ranges; values are sampled on and around the limit. |
| Multiple coverage items per requirement | Decision Table Testing (DT) | Independent conditions can co-fail even when each is correct in isolation. |
| State transition (white box) | State Transition Testing (ST) | Behaviour is best modelled as a finite state machine; coverage criteria select the exhaustiveness. |
| `fallback` / `unknown` | Manual Review | When the engine cannot infer intent, the case is emitted but flagged for human attention. |

---

## 4. Risk-Based Coverage Depth

Coverage budgets are finite; the strategy therefore allocates depth
in proportion to risk level. The rule is recorded in Table 2.

**Table 2.** Risk-to-depth rule.

| Risk level | Depth | Concrete behaviour |
|---|---|---|
| High | Maximum | Every generated case is retained; boundary, negative, and decision-table cases receive the most defence. |
| Medium | Balanced | One representative per coverage type is retained, together with every decision-table case. |
| Low | Minimal | Cases are deduplicated by coverage type; at least one case is always retained per requirement. |

Prioritisation respects the same intent: higher risk, stronger
technique, and harder coverage type are scheduled first.

---

## 5. Coverage Metrics on the Baseline

Running the rule pipeline on
[data/mini_ecommerce_requirements.json](../data/mini_ecommerce_requirements.json)
produces the reproducible baseline persisted to
[data/baseline/test_cases.json](../data/baseline/test_cases.json).
The black-box rule pipeline contributes sixty-one cases; the
white-box state-transition engine of §3 contributes a further four
for the order-status requirement, giving sixty-five cases in the
persisted baseline. Aggregate counts are recorded in Tables 3 to 5.

**Table 3.** Aggregate coverage on the baseline.

| Aggregate | Count |
|---|---:|
| Coverage items (black box) | 37 |
| Black-box test cases generated | 61 |
| White-box state-transition cases | 4 |
| Total cases in the baseline | 65 |
| After risk-based minimisation (black box) | 55 |

**Table 4.** Distribution by technique.

| Technique | Cases |
|---|---:|
| Equivalence Partitioning | 26 |
| Boundary Value Analysis | 11 |
| Decision Table Testing | 24 |
| State Transition Testing | 4 |
| **Total** | **65** |

**Table 5.** Distribution by priority (derived from the risk level).

| Priority | Cases |
|---|---:|
| High | 15 |
| Medium | 30 |
| Low | 20 |

The four white-box state-transition cases carry a Medium priority
(REQ-012 is rated Medium in the risk register), so they fall in the
Medium row.

---

## 6. Trade-Offs of the Minimisation

The minimisation step is a deliberate trade-off between cost and
confidence:

- *Low-risk requirements with redundant coverage* are collapsed to a
  small representative set.
- *Medium-risk requirements* retain one representative per coverage
  type and **all** decision-table combinations, because combinations
  often reveal cross-condition defects that single-condition tests
  miss.
- *High-risk requirements* are left untouched; the additional
  execution time is inexpensive in comparison with a missed defect.

The optimiser guarantees that no requirement is left uncovered, so
the minimised suite never abandons a requirement.

---

## 7. Robustness

The strategy is defensive at three points:

1. The black-box engine accepts both `{"coverages": …}` and
   `{"coverage": …}` shapes for the coverage input.
2. Missing risk information defaults to Medium / 5 / Medium priority
   so that the pipeline continues to produce output.
3. Coverage items typed as `fallback` or `unknown` are emitted as
   manual-review cases rather than silently dropped — the cases are
   visible to the tester and easy to catch at review.

---

## 8. Conclusion

The strategy applies the three coverage decisions — what, how, to
what depth — under the risk-based testing principle. Its application
to the Mini-E-Commerce backend produces a sixty-five-case baseline
(sixty-one black-box cases that minimise to fifty-five while
preserving full coverage, plus four white-box state-transition
cases), and concentrates effort on the order workflow at which the
three real defects of
[test_result_analysis.md](test_result_analysis.md) are detected.

---

## References

- ISO/IEC/IEEE 29119-1:2022, *Software and systems engineering — Software testing — Part 1: General concepts*.
- ISO/IEC/IEEE 29119-4:2021, *Part 4: Test techniques*.
