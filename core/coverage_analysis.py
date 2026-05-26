import json

def generate_length_coverage(constraint):
    field = constraint.get("field")
    coverage = []

    min_v = constraint.get("min")
    max_v = constraint.get("max")

    if min_v is not None:
        coverage.extend([
            {
                "description": f"{field} length = {min_v - 1}",
                "type": "boundary"
            },
            {
                "description": f"{field} length = {min_v}",
                "type": "boundary"
            },
            {
                "description": f"{field} length = {min_v + 1}",
                "type": "boundary"
            }
        ])

    if max_v is not None:
        coverage.extend([
            {
                "description": f"{field} length = {max_v - 1}",
                "type": "boundary"
            },
            {
                "description": f"{field} length = {max_v}",
                "type": "boundary"
            },
            {
                "description": f"{field} length = {max_v + 1}",
                "type": "boundary"
            }
        ])

    return coverage

def generate_required_coverage(constraint):
    field = constraint.get("field")

    return [
        {"description": f"{field} is a legal value", "type": "positive"},
        {"description": f"{field} is empty", "type": "boundary"}
    ]

def generate_existence_coverage(constraint):

    field = constraint.get("field")

    return [
        {
            "description": f"existing {field}",
            "type": "positive"
        },
        {
            "description": f"non-existing {field}",
            "type": "negative"
        },
        {
            "description": f"null {field}",
            "type": "boundary"
        }
    ]

def generate_unique_coverage(constraint):
    field = constraint.get("field")

    return [
        {"description": f"{field} already exists", "type": "negative"},
        {"description": f"{field} is new unique value", "type": "positive"},
        {"description": f"{field} is empty", "type": "boundary"}
    ]

def generate_charset_coverage(constraint):
    required = constraint.get("required", [])

    items = []

    for r in required:
        not_missing = [x for x in required if x != r]
        items.append({
            "description": f"missing {r} (has {not_missing})",
            "type": "negative"
        })

    items.append({
        "description": f"contains all required: {required}",
        "type": "positive"
    })

    return items

def generate_pattern_coverage(constraint):
    allowed = constraint.get("allowed", [])

    items = []

    for r in allowed:
        items.append({
            "description": f" {r} in input",
            "type": "positive"
        })

    items.append({
        "description": f"contains input out of allowed pattern",
        "type": "negative"
    })

    return items

def generate_enum_coverage(constraint):
    allowed = constraint.get("allowed", [])

    items = []

    for r in allowed:
        items.append({
            "description": f" {r} in enumeration",
            "type": "positive"
        })

    items.append({
        "description": f"contains input out of allowed enumeration",
        "type": "negative"
    })

    return items

def generate_numeric_range_coverage(constraint):
    field = constraint.get("field")
    coverage = []

    min_v = constraint.get("min")
    max_v = constraint.get("max")

    if min_v is not None:
        coverage.extend([
            {
                "description": f"{field} = {min_v - 1}",
                "type": "boundary"
            },
            {
                "description": f"{field} = {min_v}",
                "type": "boundary"
            },
            {
                "description": f"{field} = {min_v + 1}",
                "type": "boundary"
            }
        ])

    if max_v is not None:
        coverage.extend([
            {
                "description": f"{field} = {max_v - 1}",
                "type": "boundary"
            },
            {
                "description": f"{field} = {max_v}",
                "type": "boundary"
            },
            {
                "description": f"{field} = {max_v + 1}",
                "type": "boundary"
            }
        ])

    return coverage

def generate_relational_coverage(constraint):

    field = constraint.get("field")
    operator = constraint.get("operator")
    target = constraint.get("target")

    coverage = []

    if operator == "<=":

        coverage.extend([
            {
                "description": f"{field} less than {target}",
                "type": "positive"
            },
            {
                "description": f"{field} equals {target}",
                "type": "boundary"
            },
            {
                "description": f"{field} greater than {target}",
                "type": "negative"
            }
        ])

    elif operator == "<":

        coverage.extend([
            {
                "description": f"{field} less than {target}",
                "type": "positive"
            },
            {
                "description": f"{field} equals {target}",
                "type": "negative"
            },
            {
                "description": f"{field} greater than {target}",
                "type": "negative"
            }
        ])

    elif operator == ">=":

        coverage.extend([
            {
                "description": f"{field} greater than {target}",
                "type": "positive"
            },
            {
                "description": f"{field} equals {target}",
                "type": "boundary"
            },
            {
                "description": f"{field} less than {target}",
                "type": "negative"
            }
        ])

    elif operator == ">":

        coverage.extend([
            {
                "description": f"{field} greater than {target}",
                "type": "positive"
            },
            {
                "description": f"{field} equals {target}",
                "type": "negative"
            },
            {
                "description": f"{field} less than {target}",
                "type": "negative"
            }
        ])

    else:

        coverage.append({
            "description": f"unknown relational operator {operator}",
            "type": "unknown"
        })

    return coverage

def generate_coverage_for_requirement(req):
    coverage_items = []

    for c in req.get("constraints", []):
        ctype = c.get("type")

        if ctype == "length":
            coverage_items += generate_length_coverage(c)

        elif ctype == "unique":
            coverage_items += generate_unique_coverage(c)

        elif ctype == "existence":
            coverage_items += generate_existence_coverage(c)

        elif ctype == "required":
            coverage_items += generate_required_coverage(c)

        elif ctype == "charset":
            coverage_items += generate_charset_coverage(c)

        elif ctype == "pattern":
            coverage_items += generate_pattern_coverage(c)
        
        elif ctype == "enum":
            coverage_items += generate_enum_coverage(c)

        elif ctype == "numeric_range":
            coverage_items += generate_numeric_range_coverage(c)

        elif ctype == "relational":
            coverage_items += generate_relational_coverage(c)

        else:
            coverage_items.append({
                "description": f"unknown constraint type: {ctype}, manual intervention needed",
                "constraint": f"{c}",
                "type": "fallback"
            })

    return {
        "requirement_id": req.get("requirement_id"),
        "feature": req.get("feature"),
        "coverage_items": coverage_items
    }

def generate_coverage(parsed_requirements_json):
    all_results = []

    for req in parsed_requirements_json.get("requirements", []):
        all_results.append(generate_coverage_for_requirement(req))

    return {
        "coverages": all_results
    }