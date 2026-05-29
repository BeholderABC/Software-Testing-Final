# Coverage Item Schema

## Abstract

This document defines the shape of a coverage object produced by the
coverage engine of AutoTestDesign and consumed by the test-case
engine. A coverage object groups, per requirement, the list of
*coverage items* — observable scenarios derived from the constraint
catalogue of [constraint_schema.md](constraint_schema.md). The schema
is normative for both the language-model-driven path and the
deterministic rule fallback.

---

## 1. Overview

A coverage item is the unit of work allocated to the test-case
engine: every item is realised by at least one generated test case
([coverage_strategy.md](coverage_strategy.md) §2). The permitted item
types are recorded in Table 1.

**Table 1.** Coverage item types.

| Type | Meaning |
|---|---|
| `positive` | The happy path for a constraint. |
| `negative` | A violation of a constraint. |
| `boundary` | A value on or immediately adjacent to a limit. |
| `combination` | A combination of conditions across constraints. |
| `fallback` | The originating constraint type is outside the catalogue. |
| `unknown` | The intent could not be inferred by the engine. |

---

## 2. Canonical Shape

```json
{
  "coverages": [
    {
      "requirement_id": "REQ-001",
      "feature": "User registration",
      "coverage_items": [
        {
          "description": "username already exists",
          "type": "negative"
        },
        {
          "description": "username is new unique value",
          "type": "positive"
        },
        {
          "description": "username is empty",
          "type": "boundary"
        }
      ]
    },
    {
      "requirement_id": "REQ-002",
      "feature": "User registration",
      "coverage_items": [
        { "description": "password length = 7",  "type": "boundary" },
        { "description": "password length = 8",  "type": "boundary" },
        { "description": "password length = 9",  "type": "boundary" },
        { "description": "password length = 19", "type": "boundary" },
        { "description": "password length = 20", "type": "boundary" },
        { "description": "password length = 21", "type": "boundary" }
      ]
    },
    {
      "requirement_id": "REQ-003",
      "feature": "User registration",
      "coverage_items": [
        { "description": "missing uppercase (has ['lowercase', 'digit'])",        "type": "negative" },
        { "description": "missing lowercase (has ['uppercase', 'digit'])",        "type": "negative" },
        { "description": "missing digit (has ['uppercase', 'lowercase'])",        "type": "negative" },
        { "description": "contains all required: ['uppercase', 'lowercase', 'digit']", "type": "positive" }
      ]
    }
  ]
}
```

The top-level key is `coverages`. The legacy key `coverage` is
tolerated by the engine for the benefit of older fixtures but is not
emitted by the current pipeline.

---

## 3. Fallback Coverage Items

When the parser emits a constraint whose `type` is outside the
catalogue of [constraint_schema.md](constraint_schema.md), the
coverage engine substitutes a fallback item of the shape recorded
below.

```json
{
  "description": "unknown constraint type: <ctype>, manual intervention needed",
  "constraint": "<the offending constraint object>",
  "type": "fallback"
}
```

A fallback item is not silently dropped; the optimiser flags the
derived case with `need_manual_review = true` so that a tester
addresses it during review.

---

## References

- [constraint_schema.md](constraint_schema.md) — the constraint
  catalogue from which coverage items are derived.
- [coverage_strategy.md](coverage_strategy.md) — the strategy that
  selects techniques for each coverage item.
- [STYLE_GUIDE.md](STYLE_GUIDE.md) §3.3 — the parent JSON shape.
