"""LLM-as-a-judge for hint relevance and preciseness."""
import argparse
import json
import os
import re

from common import load_cwe_catalog, read_jsonl, write_jsonl
from llm_api import chat
from models import TEMPERATURE_BY_TASK, resolve
import prompts as P


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input_file", required=True)
    ap.add_argument("-o", "--output_file", required=True)
    ap.add_argument("--judge", default="gpt-4o", help="judge model (API model, default gpt-4o)")
    args = ap.parse_args()

    _, judge_id = resolve(args.judge)
    temp = TEMPERATURE_BY_TASK["judge"]
    catalog = load_cwe_catalog()

    done = {}
    if os.path.exists(args.output_file):
        done = {r["id"]: r for r in read_jsonl(args.output_file)}
    records = read_jsonl(args.input_file)
    out = []
    for i, r in enumerate(records, 1):
        if r["id"] in done:
            out.append(done[r["id"]])
            continue
        cwe = catalog.get(r["cwe_id"])
        if cwe is None:
            out.append({"id": r["id"], "cwe_id": r["cwe_id"], "relevant": None, "matched_hint": "",
                        "precise": None, "category": "unjudged"})
            continue
        definition = cwe.get("description") or ""
        rel = parse_json(chat(
            [{"role": "system", "content": P.JUDGE_SYSTEM},
             {"role": "user", "content": P.JUDGE_RELEVANCE.format(
                 cwe_id=r["cwe_id"], cwe_name=cwe["name"], cwe_definition=definition, hints=r["response"].strip())}],
            judge_id, temperature=temp, max_tokens=512))
        relevant = bool(rel.get("relevant"))
        matched = rel.get("matched_hint", "") or ""
        precise = None
        if relevant:
            pre = parse_json(chat(
                [{"role": "system", "content": P.JUDGE_SYSTEM},
                 {"role": "user", "content": P.JUDGE_PRECISENESS.format(
                     cwe_id=r["cwe_id"], cwe_name=cwe["name"], cwe_definition=definition, hint=matched or r["response"].strip())}],
                judge_id, temperature=temp, max_tokens=512))
            precise = bool(pre.get("precise"))
        category = "relevant_precise" if precise else ("relevant" if relevant else "irrelevant")
        out.append({"id": r["id"], "cwe_id": r["cwe_id"], "relevant": relevant, "matched_hint": matched,
                    "precise": precise, "category": category})
        if i % 10 == 0 or i == len(records):
            write_jsonl(out, args.output_file)
            print(f"  [{i}/{len(records)}]")
    write_jsonl(out, args.output_file)
    counts = {}
    for r in out:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    print(f"done -> {args.output_file}  {counts}")


if __name__ == "__main__":
    main()
