# Constraint Schema

## Abstract

This document defines the constraint vocabulary emitted by the
requirement parser and consumed by the coverage engine of
AutoTestDesign. Nine constraint types are defined, each with an exact
field layout. The vocabulary is closed: producers must not emit values
outside this catalogue, and consumers may rely on the presence of the
declared fields. The schema is normative for both the
language-model-driven parser and the deterministic rule fallback so
that downstream stages remain agnostic to the producer.

---

## 1. Overview

A constraint is the structured representation of a rule that a field
of a requirement must satisfy. Each constraint object is a member of
the `constraints` array of a parsed requirement
(see [STYLE_GUIDE.md](STYLE_GUIDE.md) §3.1) and is identified by its
`type`. The permitted types are recorded in Table 1.

**Table 1.** Constraint types.

| Type | Purpose |
|---|---|
| `length` | Bounds the length of a string field. |
| `unique` | Asserts uniqueness of the field across persisted records. |
| `existence` | Asserts that the referenced record exists. |
| `required` | Asserts that the field is present and non-empty. |
| `charset` | Enumerates required character classes. |
| `pattern` | Restricts the field to a regular-expression class. |
| `enum` | Restricts the field to an enumerated set. |
| `numeric_range` | Bounds a numeric field. |
| `relational` | Relates one field to another by an operator. |

---

## 2. Field Layouts

### 2.1 `length`

```json
{
  "field": "password",
  "type": "length",
  "min": 8,
  "max": 20
}
```

The `min` and `max` keys are integers; at least one is required.

### 2.2 `unique`

```json
{
  "field": "username",
  "type": "unique"
}
```

### 2.3 `existence`

```json
{
  "field": "id",
  "type": "existence"
}
```

### 2.4 `required`

```json
{
  "field": "email",
  "type": "required"
}
```

### 2.5 `charset`

```json
{
  "field": "password",
  "type": "charset",
  "required": ["uppercase", "lowercase", "digit"]
}
```

The `required` array enumerates the character classes that must each
be present at least once. The canonical class names are `uppercase`,
`lowercase`, `digit`, and `symbol`.

### 2.6 `pattern`

```json
{
  "field": "email",
  "type": "pattern",
  "regex": "^[^@]+@[^@]+\\.[^@]+$"
}
```

The `regex` field carries a Python-compatible regular expression.

### 2.7 `enum`

```json
{
  "field": "status",
  "type": "enum",
  "allowed": ["pending", "completed", "cancelled"]
}
```

### 2.8 `numeric_range`

```json
{
  "field": "price",
  "type": "numeric_range",
  "min": 1
}
```

Either or both of `min` and `max` may appear. Bounds are inclusive.

### 2.9 `relational`

```json
{
  "field": "quantity",
  "type": "relational",
  "operator": "<=",
  "target": "stock"
}
```

The permitted operators are `<`, `<=`, `=`, `!=`, `>=`, and `>`. The
`target` field references the name of the related field.

---

## 3. Vocabulary Discipline

The catalogue is closed. The historical synonyms `character_set` and
`num_range` are explicitly prohibited; the canonical forms `charset`
and `numeric_range` are the only acceptable substitutes. Any
constraint that the parser cannot map onto the catalogue is recorded
verbatim and a `fallback` coverage item is emitted by the coverage
engine (see [coverage_item_schema.md](coverage_item_schema.md) §3).

---

## References

- [STYLE_GUIDE.md](STYLE_GUIDE.md) §3.1 — parsed-requirement schema.
- [coverage_item_schema.md](coverage_item_schema.md) — downstream
  coverage-item shapes derived from this catalogue.
