import json
from core import utils
from dotenv import load_dotenv
from openai import OpenAI
import os
from pathlib import Path


load_dotenv()
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "parser_prompt.txt"
client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL")
)

def parse_requirement(requirement_text):

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
                "content": requirement_text
            }
        ],
        temperature=0
    )

    result = response.choices[0].message.content
    result = utils.extract_json(result)
    return json.loads(result)