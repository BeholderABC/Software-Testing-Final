from core.risk_analysis import analyze_risks
import json
from pathlib import Path

SAMPLE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_json_requirements.json"

with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
    sample = f.read()

risk = analyze_risks(json.loads(sample))

print(json.dumps(risk, indent=2))