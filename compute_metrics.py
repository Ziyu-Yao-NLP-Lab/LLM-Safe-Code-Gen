"""Compute TarV-R and AllV-R from CodeQL results."""
import argparse
from collections import defaultdict

from common import load_sarif, read_json, read_jsonl, write_json


def load_run(index_path, sarif_path):
    index = read_json(index_path)
    files = load_sarif(sarif_path, index)
    out = {}
    for fname, meta in index.items():
        if fname in files:
            out[meta["id"]] = set(files[fname]["cwes"])
    return out


def rates(sample_ids, detected, target_of):
    n = len(sample_ids)
    n_tar = sum(1 for s in sample_ids if target_of[s] in detected.get(s, set()))
    n_all = sum(1 for s in sample_ids if detected.get(s))
    return {"n": n, "n_target": n_tar, "n_any": n_all,
            "TarV-R": round(100 * n_tar / n, 2) if n else None,
            "AllV-R": round(100 * n_all / n, 2) if n else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--sarif", required=True, help="CodeQL SARIF output for --index")
    ap.add_argument("-o", "--output_file", required=True)
    ap.add_argument("--denominator", choices=["analyzed", "all"], default="analyzed")
    ap.add_argument("--fallback_index")
    ap.add_argument("--fallback_sarif")
    ap.add_argument("--labels")
    ap.add_argument("--baseline_index")
    ap.add_argument("--baseline_sarif")
    args = ap.parse_args()

    tasks = read_jsonl(args.tasks)
    target_of = {t["id"]: t["cwe_id"] for t in tasks}
    detected = load_run(args.index, args.sarif)
    if args.fallback_index:
        fb = load_run(args.fallback_index, args.fallback_sarif)
        for k, v in fb.items():
            detected.setdefault(k, v)

    ids = [t["id"] for t in tasks]
    analysed = [i for i in ids if i in detected]
    sample_ids = ids if args.denominator == "all" else analysed
    result = {"denominator": args.denominator, "n_tasks": len(ids), "n_analyzed": len(analysed),
              "overall": rates(sample_ids, detected, target_of)}

    per_cwe = defaultdict(list)
    for s in sample_ids:
        per_cwe[target_of[s]].append(s)
    result["per_cwe"] = {c: rates(v, detected, target_of) for c, v in sorted(per_cwe.items(), key=lambda kv: int(kv[0]))}

    baseline = None
    if args.baseline_index:
        baseline = load_run(args.baseline_index, args.baseline_sarif)
        result["baseline_overall"] = rates(sample_ids, baseline, target_of)

    if args.labels:
        cats = defaultdict(list)
        for r in read_jsonl(args.labels):
            if r["id"] in target_of and r["id"] in set(sample_ids):
                cats[r["category"]].append(r["id"])
        result["by_hint_category"] = {}
        for c, v in cats.items():
            entry = rates(v, detected, target_of)
            if baseline is not None:
                entry["baseline"] = rates(v, baseline, target_of)
            result["by_hint_category"][c] = entry

    write_json(result, args.output_file)
    o = result["overall"]
    print(f"samples={o['n']}  TarV-R={o['TarV-R']}%  AllV-R={o['AllV-R']}%   (analysed {len(analysed)}/{len(ids)})")
    if baseline is not None:
        b = result["baseline_overall"]
        print(f"baseline on the same samples: TarV-R={b['TarV-R']}%  AllV-R={b['AllV-R']}%")
    if args.labels:
        for c, e in result["by_hint_category"].items():
            base = f"  (baseline TarV-R {e['baseline']['TarV-R']}%)" if "baseline" in e else ""
            print(f"  {c:<18} n={e['n']:<5} TarV-R={e['TarV-R']}%{base}")
    print(f"-> {args.output_file}")


if __name__ == "__main__":
    main()
