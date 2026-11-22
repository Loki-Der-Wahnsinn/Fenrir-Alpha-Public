import ast
import json
import os
import re


def extract_json_from_llm_output(code: str) -> str:
    """Extracts and cleans JSON payloads from LLM output."""
    code = re.sub(r"<think>.*?</think>", "", code, flags=re.DOTALL | re.IGNORECASE)
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", code, re.DOTALL | re.IGNORECASE)
    json_str = match.group(1).strip() if match else code.strip()
    first_brace = json_str.find("{")
    last_brace = json_str.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
        json_str = json_str[first_brace : last_brace + 1]
    return json_str


def brute_force_repair_json(json_str: str) -> dict:
    """Attempts to parse and minimally repair malformed JSON objects."""
    json_str = re.sub(r"<think>.*?</think>", "", json_str, flags=re.DOTALL | re.IGNORECASE)
    first_brace = json_str.find("{")
    last_brace = json_str.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace >= first_brace:
        json_str = json_str[first_brace : last_brace + 1]

    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        if not json_str.endswith("}"):
            json_str += "\n}"
        if '"code": "' in json_str and not json_str.rstrip().endswith('"}'):
            json_str = json_str.rstrip()
            if not json_str.endswith('"'):
                json_str += '"'
            json_str += "\n}"
        try:
            data = json.loads(json_str, strict=False)
        except json.JSONDecodeError:
            try:
                clean_str = json_str.replace("\\n", "\n")
                data = ast.literal_eval(clean_str)
                if not isinstance(data, dict):
                    raise ValueError
            except Exception:
                data = {"action": "create_skill", "code": "", "target_file": "error_skill.py"}

    if data.get("action") not in ["create_skill", "add_method", "execute_skill"]:
        data["action"] = "create_skill"
    return data


def sanitize_target_filename(raw_target: str, cycle: int) -> str:
    """Normalizes a filename into a valid Python module filename."""
    target_basename = os.path.basename(raw_target)
    if target_basename.endswith(".py"):
        target_basename = target_basename[:-3]
    target_basename = re.sub(r"[^a-zA-Z0-9_]", "_", target_basename)
    target_basename = re.sub(r"_+", "_", target_basename).strip("_")
    if not target_basename or target_basename == "Exakte_Datei_aus_EXISTIERENDE_SKILLS":
        target_basename = f"skill_cycle_{cycle}"
    return target_basename + ".py"
