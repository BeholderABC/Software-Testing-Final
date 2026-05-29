# Style Guide

## Abstract

This document records the conventions adopted across the
AutoTestDesign project for terminology, identifiers, JSON schemas,
file naming, and prose style. The conventions apply uniformly to
every document, source module, prompt template, and submission
artefact. Their purpose is to keep the controlled vocabulary
consistent between the language-model-driven stages and the
deterministic engines and to ensure that every cross-reference, every
schema field, and every identifier resolves unambiguously.

---

## 1. Terminology

### 1.1 Test design techniques

**Table 1.** Test design techniques and their domain of application.

| Technique | Abbreviation | Domain of application |
|---|---|---|
| Equivalence Partitioning | EP | Black box; `positive` and `negative` coverage items. |
| Boundary Value Analysis | BVA | Black box; `boundary` coverage items. |
| Decision Table Testing | DT | Black box; multi-condition combinations. |
| State Transition Testing | ST | White box; driven by [data/order_state_model.json](../data/order_state_model.json) (FR 4.0). |
| Manual Review | MR | Fallback or unknown coverage items requiring human judgement. |

Each technique is spelled in full at first occurrence within a
section; the abbreviation is used thereafter.

### 1.2 Pipeline vocabulary

**Table 2.** Pipeline vocabulary and forms to be avoided.

| Term | Definition | Forms to avoid |
|---|---|---|
| Requirement | One specified system behaviour. | requirements doc, spec |
| Structured requirement | A requirement parsed into schema v1. | parsed requirement |
| Coverage item | An observable scenario derived from a constraint. | coverage point |
| Coverage strategy | The procedure that generates a family of coverage items. | coverage approach |
| Test case | A concrete, executable verification. | test scenario |
| Test suite | A collection of test cases. | test set |
| Test oracle | A structured expected outcome. | expected output |
| Traceability | The forward or backward link from requirement to test. | trace, link |
| Test suite optimisation | Prioritisation followed by minimisation. | suite reduction |
| Target application | The system under test. | SUT (permitted; not preferred) |
| Designer | The tester operating the tool. | user (insufficiently specific) |

### 1.3 Risk and priority vocabulary

**Table 3.** Risk and priority field values.

| Field | Permitted values |
|---|---|
| `risk_level` | `High`, `Medium`, `Low` (title-case) |
| `risk_score` | Integer in `[1, 10]` |
| `priority` | `High`, `Medium`, `Low` |

### 1.4 Coverage item types

The permitted coverage types are `positive`, `negative`, `boundary`,
`combination`, `fallback`, and `unknown`, all in lowercase. No other
values are emitted.

### 1.5 Constraint types

The permitted constraint types are `length`, `unique`, `existence`,
`required`, `charset`, `pattern`, `enum`, `numeric_range`, and
`relational`, all in lowercase. The form `charset` is canonical;
`character_set` is not used. The form `numeric_range` is canonical;
`num_range` is not used.

---

## 2. Identifiers

### 2.1 Entity identifiers

**Table 4.** Identifier formats.

| Entity | Format | Example |
|---|---|---|
| Requirement | `REQ-NNN` | `REQ-007` |
| Coverage item | `CI-NNN` | `CI-017` |
| Test case | `TC-{REQ-ID}-NNN` | `TC-REQ-009-002` |
| Risk dimension | `snake_case` | `business_impact` |
| Output timestamp | `YYYYMMDD_HHMMSS` | `20260528_204249` |

The short forms `R1`, `R2`, … are restricted to the toy fixtures in
[data/](../data/) prefixed `sample_` and the unit tests that consume
them. All deliverables and the Mini-E-Commerce dataset use
`REQ-NNN`.

### 2.2 File naming

**Table 5.** File-naming rules.

| Kind | Rule | Example |
|---|---|---|
| Python module | `snake_case.py` | `coverage_analysis.py` |
| Markdown document | `snake_case.md` with no personal suffix | `test_plan.md` |
| Data JSON | `snake_case.json` | `mini_ecommerce_requirements.json` |
| Output artefact | `{kind}_{timestamp}.{ext}` | `test_cases_20260528_204249.json` |
| Screenshot | `{NN}_{slug}.png` | `08_run_tests.png` |

### 2.3 Python style

**Table 6.** Python source conventions.

| Element | Convention |
|---|---|
| Functions and variables | `snake_case` |
| Classes | `PascalCase` |
| Constants and enumerations | `UPPER_SNAKE_CASE` |
| Private helpers | leading underscore (e.g., `_extract_test_cases`) |
| Module docstring | triple-quoted; declares purpose and key exports |

---

## 3. JSON Schema v1

The shapes recorded below are shared by the language-model-driven
stages and the deterministic rule engines. The contract is single-
sourced so that downstream modules need not branch on the producer.

### 3.1 Parsed requirement

```jsonc
{
  "requirements": [
    {
      "requirement_id": "REQ-001",
      "feature": "string",
      "inputs": ["field_name"],
      "constraints": [
        { "field": "password", "type": "length", "min": 8, "max": 20 }
      ],
      "conditions": ["string"],
      "expected_behavior": ["string"]
    }
  ]
}
```

### 3.2 Risk assessment

```jsonc
{
  "risk_assessment": [
    {
      "requirement_id": "REQ-001",
      "feature": "string",
      "risk_level": "High",
      "risk_score": 8,
      "factors": ["string", "..."]
    }
  ]
}
```

### 3.3 Coverage

```jsonc
{
  "coverages": [
    {
      "requirement_id": "REQ-001",
      "feature": "string",
      "coverage_items": [
        { "description": "string", "type": "positive" }
      ]
    }
  ]
}
```

### 3.4 Test case

```jsonc
{
  "test_cases": [
    {
      "test_case_id": "TC-REQ-001-001",
      "requirement_id": "REQ-001",
      "feature": "string",
      "title": "string",
      "description": "string",
      "test_design_technique": "Equivalence Partitioning",
      "coverage_item": "string",
      "coverage_type": "positive",
      "preconditions": ["string"],
      "test_data": { "field": "value" },
      "steps": ["string"],
      "expected_result": "string",
      "oracle": {
        "http_status_min": 200,
        "http_status_max": 201,
        "must_contain": ["keyword"],
        "must_not_contain": [],
        "side_effect": {}
      },
      "priority": "High",
      "risk_level": "High",
      "risk_score": 8,
      "traceability": {
        "source_requirement": "REQ-001",
        "covered_item": "string",
        "coverage_strategy": "positive path coverage"
      },
      "review_status": "generated",
      "need_manual_review": false
    }
  ],
  "summary": {
    "total": 19,
    "by_technique": { "Equivalence Partitioning": 6 },
    "by_priority":  { "High": 4, "Medium": 7, "Low": 8 }
  }
}
```

### 3.5 Optimisation result

```jsonc
{
  "optimized_test_cases": [/* identical shape to test_cases */],
  "optimization_summary": {
    "original_count": 19,
    "optimized_count": 11,
    "strategy": "risk_based_minimization",
    "removed_count": 8
  }
}
```

---

## 4. Cross-Cutting Rules

### 4.1 Canonical constraint spelling

The form `charset` is canonical and `character_set` is not used.

### 4.2 Risk-score range

The `risk_score` field is an integer in `[1, 10]`. Its mapping to
`risk_level` is recorded in Table 7.

**Table 7.** Risk score to risk level.

| Score | Level |
|---|---|
| 1 – 3 | Low |
| 4 – 7 | Medium |
| 8 – 10 | High |

### 4.3 Top-level keys per producer

**Table 8.** Top-level JSON keys.

| Producer | Top-level key |
|---|---|
| Parser | `requirements` |
| Risk analyser | `risk_assessment` |
| Coverage engine | `coverages` |
| Test-case engine | `test_cases` |
| Optimiser | `optimized_test_cases` |

### 4.4 Risk level to priority

A one-to-one mapping applies (`High`→`High`, `Medium`→`Medium`,
`Low`→`Low`). When risk information is absent the defaults are
`risk_level=Medium`, `risk_score=5`, `priority=Medium`.

---

## 5. Writing Style

### 5.1 Headings

Level 1 denotes the document title. Section headings begin at level
2. Level 4 is reserved for the rare cases in which a finer
subdivision is required.

### 5.2 References

**Table 9.** Cross-reference formats.

| Target | Format | Example |
|---|---|---|
| File | `[name](relative/path)` | `[core/parser.py](../core/parser.py)` |
| Line | `[name:NN](relative/path#LNN)` | `[app.py:474](../app.py#L474)` |

File paths are not wrapped in backticks because the IDE preview can
no longer navigate them.

### 5.3 Tables

Column headers are bolded only where emphasis is required. Standard
`|---|` alignment markers are used; centred alignment renders
inconsistently across viewers and is therefore not used.

### 5.4 Code blocks

**Table 10.** Code-fence language hints.

| Content | Fence |
|---|---|
| Python | ```` ```python ```` |
| Shell | ```` ```bash ```` |
| JSON with comments | ```` ```jsonc ```` |
| Pure JSON | ```` ```json ```` |

The language is declared on the fence rather than as a preceding
comment.

### 5.5 Diagrams

Mermaid is used for flowcharts, state diagrams, and sequence
diagrams, so that the rendering is native to Markdown. Slide-deck
artwork is exported at width ≥ 1920 px.

### 5.6 Language mixing

When Chinese prose contains English terms or numbers, a half-width
space is inserted on both sides (e.g., `包含 19 条测试用例`).
Full-width punctuation is used in Chinese prose; identifiers, file
names, JSON, and shell commands retain ASCII punctuation regardless.

### 5.7 Risk dimensions

**Table 11.** Risk-dimension labels.

| Field | Display label |
|---|---|
| `business_impact` | Business impact |
| `failure_probability` | Failure probability |
| `complexity` | Complexity |
| `failure_impact` | Failure impact |

---

## 6. Presentation Rules

**Table 12.** Presentation conventions.

| Slot | Rule |
|---|---|
| Cover slide | Team identifier, full names, and student numbers (per assignment requirement). |
| Body fonts | Chinese: Source Han Sans or PingFang. English: Helvetica or Inter. |
| Title size | ≥ 32 pt |
| Body size | ≥ 20 pt |
| Risk colour palette | Red, amber, and green for High, Medium, and Low respectively. |
| Demo screenshots | Taken from [screenshots/](../screenshots/) so that they reflect the live UI. |

---

## 7. Git Hygiene

Commit messages are written in the imperative present, in English,
with a subject line of at most seventy-two characters
(e.g., *Wire coverage_analysis into the UI pipeline*). Branches are
named under the prefixes `feat/<short-desc>`, `fix/<short-desc>`,
or `docs/<short-desc>`. The offline unit tests are executed prior
to every push.

---

## 8. Self-Check Before Submission

Before any change is merged the following checks are performed.

1. Terminology conforms to §1.
2. New identifiers and file names conform to §2.
3. New JSON shapes conform to §3.
4. No banned strings appear (`character_set`, `num_range`, `R1` in
   production data, personal suffixes on document file names).
5. Writing style conforms to §5.
6. Diagrams and screenshots conform to §5.5 and §6.
7. The offline unit tests pass.

---

## References

- ISO/IEC/IEEE 29119-1:2022, *Software and systems engineering — Software testing — Part 1: General concepts*.
- International Software Testing Qualifications Board (ISTQB), *Foundation Level Syllabus*, 2018.
