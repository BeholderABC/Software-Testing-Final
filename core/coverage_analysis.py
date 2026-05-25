import json


def generate_length_coverage(constraint):
    field = constraint.get("field")
    min_v = constraint.get("min")
    max_v = constraint.get("max")

    return [
        {"description": f"{field} length = {min_v - 1}", "type": "boundary"},
        {"description": f"{field} length = {min_v}", "type": "boundary"},
        {"description": f"{field} length = {min_v + 1}", "type": "boundary"},
        {"description": f"{field} length = {max_v - 1}", "type": "boundary"},
        {"description": f"{field} length = {max_v}", "type": "boundary"},
        {"description": f"{field} length = {max_v + 1}", "type": "boundary"},
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


def generate_coverage_for_requirement(req):
    coverage_items = []

    for c in req.get("constraints", []):
        ctype = c.get("type")

        if ctype == "length":
            coverage_items += generate_length_coverage(c)

        elif ctype == "unique":
            coverage_items += generate_unique_coverage(c)

        elif ctype == "character_set":
            coverage_items += generate_charset_coverage(c)

        else:
            coverage_items.append({
                "description": f"unknown constraint type: {ctype}",
                "type": "unknown"
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
        "coverage": all_results
    }