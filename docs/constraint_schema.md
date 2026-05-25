# Constraint Types and Schema

## length
{
  "field": "password",
  "type": "length",
  "min": 8,
  "max": 20
}

## unique

{
  "field": "username",
  "type": "unique"
}

## character_set

{
  "field": "password",
  "type": "charset",
  "required": [
    "uppercase",
    "lowercase",
    "digit"
  ]
}

## required

{
  "field": "email",
  "type": "required"
}

## existence

{
  "field": "ID",
  "type": "existence"
}

## enum

{
  "field": "status",
  "type": "enum",
  "allowed": [
    "pending",
    "completed",
    "cancelled"
  ]
}

## numeric_range

{
  "field": "price",
  "type": "numeric_range",
  "min": 1
}

## relational

{
  "field": "quantity",
  "type": "relational",
  "operator": "<=",
  "target": "stock"
}

