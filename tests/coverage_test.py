from core.coverage_analysis import generate_coverage
import json
from pathlib import Path

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_json_requirements.json"

with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
    sample = f.read()
# sample = {
#     "requirements": [
#         {
#             "requirement_id": "R2",
#             "feature": "Password validation",
#             "constraints": [
#                 {"field": "password", "type": "length", "min": 8, "max": 20}
#             ]
#         }
#     ]
# }

result = generate_coverage(json.loads(sample))

print(json.dumps(result, indent=2))