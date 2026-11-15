"""Shared helpers."""
import json
import os
import re
from pathlib import Path

CWE_FILE = Path(__file__).parent / "data" / "cwe_official" / "all_cwe.json"
COVERED_CWE_FILE = Path(__file__).parent / "data" / "cwe_official" / "codeql_python_security_extended_cwes.json"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(data, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in data:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_cwe(cwe) -> str:
    """'CWE-022', 'cwe-22', 22, '022' -> '22'."""
    s = str(cwe).strip().lower()
    s = s.replace("cwe-", "").replace("cwe", "")
    s = s.lstrip("0")
    return s or "0"


def load_cwe_catalog() -> dict:
    return {normalize_cwe(k): v for k, v in read_json(CWE_FILE).items()}


def load_covered_cwes(path=None) -> set:
    return {normalize_cwe(k) for k in read_json(path or COVERED_CWE_FILE)}


_FENCE = re.compile(r"```(?:python|py)?\s*\n?(.*?)```", re.DOTALL)


def extract_code(response: str) -> str:
    """Return the first Python code block, or the whole response if unfenced."""
    if response is None:
        return ""
    blocks = _FENCE.findall(response)
    if not blocks:
        return response.strip()
    for b in blocks:
        if "import " in b or "def " in b or "class " in b:
            return b.strip()
    return blocks[0].strip()


def safe_filename(record_id: str) -> str:
    name = re.sub(r"[^\w\-.]", "_", str(record_id))
    if not name.endswith(".py"):
        name += ".py"
    return name


def load_sarif(sarif_path, file_names) -> dict:
    """CodeQL SARIF -> {file name: {"cwes": [...], "findings": [...]}} for every analysed file."""
    sarif = read_json(sarif_path)
    files = {name: {"cwes": set(), "findings": []} for name in file_names}
    for run in sarif.get("runs", []):
        rules = {}
        for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
            tags = rule.get("properties", {}).get("tags", [])
            rules[rule["id"]] = {
                "name": rule.get("name", rule["id"]),
                "cwe_ids": [normalize_cwe(t.split("/")[-1]) for t in tags if "/cwe/" in t],
                "message": rule.get("fullDescription", {}).get("text") or rule.get("shortDescription", {}).get("text", ""),
            }
        for res in run.get("results", []):
            info = rules.get(res.get("ruleId"), {"name": res.get("ruleId"), "cwe_ids": [], "message": ""})
            for loc in res.get("locations", []):
                phys = loc.get("physicalLocation", {})
                fname = Path(phys.get("artifactLocation", {}).get("uri", "")).name
                if fname not in files:
                    continue
                region = phys.get("region", {})
                files[fname]["findings"].append({
                    "rule_id": res.get("ruleId"),
                    "query_name": info["name"],
                    "cwe_ids": info["cwe_ids"],
                    "message": info["message"] or res.get("message", {}).get("text", ""),
                    "start_line": region.get("startLine"),
                    "start_column": region.get("startColumn"),
                })
                files[fname]["cwes"].update(info["cwe_ids"])
    return files
