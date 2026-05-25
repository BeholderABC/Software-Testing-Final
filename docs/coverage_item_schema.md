# Coverage Item Schema

The 
'''json
{
  "coverages": [
    {
      "requirement_id": "R1",
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
      "requirement_id": "R2",
      "feature": "User registration",
      "coverage_items": [
        {
          "description": "password length = 7",
          "type": "boundary"
        },
        {
          "description": "password length = 8",
          "type": "boundary"
        },
        {
          "description": "password length = 9",
          "type": "boundary"
        },
        {
          "description": "password length = 19",
          "type": "boundary"
        },
        {
          "description": "password length = 20",
          "type": "boundary"
        },
        {
          "description": "password length = 21",
          "type": "boundary"
        }
      ]
    },
    {
      "requirement_id": "R3",
      "feature": "User registration",
      "coverage_items": [
        {
          "description": "missing uppercase (has ['lowercase', 'digit'])",
          "type": "negative"
        },
        {
          "description": "missing lowercase (has ['uppercase', 'digit'])",
          "type": "negative"
        },
        {
          "description": "missing digit (has ['uppercase', 'lowercase'])",
          "type": "negative"
        },
        {
          "description": "contains all required: ['uppercase', 'lowercase', 'digit']",
          "type": "positive"
        }
      ]
    }
  ]
}
'