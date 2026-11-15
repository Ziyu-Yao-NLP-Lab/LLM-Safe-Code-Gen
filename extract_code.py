"""Extract Python code from model responses into .py files."""
import argparse
import os

from common import extract_code, read_jsonl, safe_filename, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input_file", required=True)
    ap.add_argument("-o", "--output_dir", required=True)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    index, skipped = {}, []
    for r in read_jsonl(args.input_file):
        code = extract_code(r.get("response", ""))
        if not code.strip():
            skipped.append(r["id"])
            continue
        fname = safe_filename(r["id"])
        with open(os.path.join(args.output_dir, fname), "w", encoding="utf-8") as f:
            f.write(code + "\n")
        index[fname] = {"id": r["id"], "dataset": r.get("dataset"), "cwe_id": r.get("cwe_id")}
    write_json(index, os.path.join(args.output_dir, "index.json"))
    write_json(skipped, os.path.join(args.output_dir, "skipped.json"))
    print(f"{len(index)} files written to {args.output_dir} ({len(skipped)} records without code)")


if __name__ == "__main__":
    main()
