import json
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import os
from core import utils

load_dotenv()
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "risk_prompt.txt"
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL")
)

def analyze_risk(requirement_json):

    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    response = client.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": json.dumps(requirement_json)
            }
        ],
        temperature=0
    )

    result = response.choices[0].message.content
    result = utils.extract_json(result)
    return json.loads(result)

_DIMENSIONS = ("business_impact", "failure_probability",
               "complexity", "failure_impact")


def _dim(value):
    """Clamp a dimension rating to the integer scale 1..3 (default 2)."""
    try:
        return max(1, min(3, int(value)))
    except (TypeError, ValueError):
        return 2


def score_from_dimensions(dims):
    """Combine four 1..3 dimension ratings into a 1..10 risk score + level.

    The four ratings sum to 4..12; that range is linearly squashed onto
    1..10 so the headline score is always a transparent function of the
    dimensions (no separate black-box number). Level follows the
    canonical mapping in docs/STYLE_GUIDE.md.
    """
    total = sum(_dim(dims.get(d)) for d in _DIMENSIONS)
    score = max(1, min(10, round((total - 4) / 8 * 9 + 1)))
    if score >= 8:
        level = "High"
    elif score >= 4:
        level = "Medium"
    else:
        level = "Low"
    return score, level


def analyze_risks(parsed_requirements_json):

    results = []

    for req in parsed_requirements_json.get("requirements", []):
        try:
            risk = analyze_risk(req)
            dims = {d: _dim(risk.get(d)) for d in _DIMENSIONS}
            score, level = score_from_dimensions(dims)

            results.append({
                "requirement_id": req.get("requirement_id"),
                "feature": req.get("feature"),
                "risk_level": level,
                "risk_score": score,
                "factors": risk.get("factors", []),
                **dims,
            })

        except Exception as e:
            # Fail soft: any single requirement's analysis can fall back
            # to a Medium / 5 default without aborting the whole batch.
            results.append({
                "requirement_id": req.get("requirement_id"),
                "feature": req.get("feature"),
                "risk_level": "Medium",
                "risk_score": 5,
                "factors": ["Fallback due to parsing error"],
                "business_impact": 2,
                "failure_probability": 2,
                "complexity": 2,
                "failure_impact": 2,
                "error": str(e)
            })

    return {
        "risk_assessment": results
    }