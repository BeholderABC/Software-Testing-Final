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

def analyze_risks(parsed_requirements_json):

    results = []

    for req in parsed_requirements_json.get("requirements", []):
        try:
            risk = analyze_risk(req)

            results.append({
                "requirement_id": req.get("requirement_id"),
                "feature": req.get("feature"),
                "risk_level": risk.get("risk_level"),
                "risk_score": risk.get("risk_score"),
                "factors": risk.get("factors", [])
            })

        except Exception as e:
            # 鲁棒性处理（很重要）
            results.append({
                "requirement_id": req.get("requirement_id"),
                "feature": req.get("feature"),
                "risk_level": "Medium",
                "risk_score": 5,
                "factors": ["Fallback due to parsing error"],
                "error": str(e)
            })

    return {
        "risk_assessment": results
    }