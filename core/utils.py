import json
import csv
from pathlib import Path


def load_requirements(source):
    """
    - string
    - .txt
    - .json
    - .csv
    """

    if not source:
        raise ValueError("Input source cannot be empty")

    path = Path(source)

    if path.exists():

        suffix = path.suffix.lower()

        # TXT
        if suffix == ".txt":
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

        # JSON
        elif suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # list[str]
            if isinstance(data, list):
                return "\n".join(data)

            # dict
            elif isinstance(data, dict):
                return json.dumps(data)

            else:
                raise ValueError("Unsupported JSON structure")

        # CSV
        elif suffix == ".csv":

            requirements = []

            with open(path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)

                for row in reader:
                    if row:
                        requirements.append(row[0])

            return "\n".join(requirements)

        else:
            raise ValueError(f"Unsupported file type: {suffix}")


    return source

def extract_json(raw_text):
    if raw_text.startswith("`") :
        start = raw_text.find("{")
        end = raw_text.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("No JSON object found")

        return raw_text[start:end + 1]

    return raw_text

def save_json(data, filename):
    OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"[Saved] {filepath}")
