"""Convert benchmarks into the common task format."""
import argparse

from common import load_covered_cwes, normalize_cwe, read_json, write_jsonl
from prompts import SECCODEPLT_TASK_DEFINITION

# stripped from CyberSecEval prompts
CYBERSECEVAL_SUFFIX = (
    "Only return the code, don't include any other information,\n"
    "    such as a preamble or suffix."
)


def seccodeplt(records):
    for r in records:
        task = SECCODEPLT_TASK_DEFINITION.format(
            description=r["task_description.description"],
            function_name=r["task_description.function_name"],
            context=r["task_description.context"],
            arguments=r["task_description.arguments"],
            return_value=r["task_description.return"],
            raise_value=r["task_description.raise"],
        )
        yield {"id": r["id"], "dataset": "seccodeplt", "cwe_id": normalize_cwe(r["CWE_ID"]), "task": task}


def securityeval(records):
    for r in records:
        yield {"id": r["id"], "dataset": "securityeval", "cwe_id": normalize_cwe(r["cwe-id"]), "task": r["prompt"]}


def cyberseceval(records):
    for r in records:
        if r.get("language") != "python":
            continue
        task = r["test_case_prompt"].replace(CYBERSECEVAL_SUFFIX, "").strip()
        cwe = normalize_cwe(r["cwe_identifier"])
        yield {"id": f"cyberseceval_{cwe}_{r['prompt_id']}", "dataset": "cyberseceval", "cwe_id": cwe, "task": task}


CONVERTERS = {"seccodeplt": seccodeplt, "securityeval": securityeval, "cyberseceval": cyberseceval}
FILTERED_BY_DEFAULT = {"seccodeplt", "cyberseceval"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-d", "--dataset", required=True, choices=sorted(CONVERTERS))
    ap.add_argument("-i", "--input_file", required=True)
    ap.add_argument("-o", "--output_file", required=True)
    ap.add_argument("--covered_cwes", default=None, help="JSON list of CWE ids the CodeQL suite can report")
    ap.add_argument("--keep_uncovered", action="store_true", help="keep tasks whose CWE is not covered by CodeQL")
    args = ap.parse_args()

    records = read_json(args.input_file)
    tasks = list(CONVERTERS[args.dataset](records))
    n_all = len(tasks)
    if args.dataset in FILTERED_BY_DEFAULT and not args.keep_uncovered:
        covered = load_covered_cwes(args.covered_cwes)
        dropped = sorted({t["cwe_id"] for t in tasks if t["cwe_id"] not in covered}, key=int)
        tasks = [t for t in tasks if t["cwe_id"] in covered]
        if dropped:
            print(f"dropped CWEs (not reportable by the suite): {', '.join(dropped)}")
    write_jsonl(tasks, args.output_file)
    print(f"{args.dataset}: {len(tasks)} tasks written ({n_all - len(tasks)} dropped) -> {args.output_file}")


if __name__ == "__main__":
    main()
