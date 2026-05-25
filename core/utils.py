
def extract_json(raw_text):
    if raw_text.startswith("`") :
        start = raw_text.find("{")
        end = raw_text.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("No JSON object found")

        return raw_text[start:end + 1]

    return raw_text
