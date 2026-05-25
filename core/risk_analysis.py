import json
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL")
)

def analyze_risk(requirement_json):

    with open("prompts/risk_prompt.txt", "r") as f:
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

    return json.loads(result)