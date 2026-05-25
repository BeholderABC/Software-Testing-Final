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
  "type": "character_set",
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

## positive

{
  "field": "amount",
  "type": "positive"
}