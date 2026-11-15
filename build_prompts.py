"""Build chat prompts for one experimental condition (--task)."""
import argparse
import sys

from common import load_cwe_catalog, load_sarif, read_json, read_jsonl, write_jsonl
import prompts as P

TASKS = [
    "vanilla", "hint_generation", "code_gen_with_hints",
    "code_gen_with_cwe_definition", "directive_hint_generation", "code_gen_with_directive_hint",
    "explained_feedback_generation", "repair_direct", "repair_explained",
]


def user(content):
    return {"role": "user", "content": content}


def assistant(content):
    return {"role": "assistant", "content": content}


def base(task_text):
    return f"{P.CODE_GEN_START}\n\n{task_text}"


def load_responses_by_id(path):
    return {r["id"]: r for r in read_jsonl(path)}


def target_cwe_block(t, catalog):
    entry = catalog.get(t["cwe_id"])
    if entry is None:
        return None
    return f"{P.TARGET_CWE_INSTRUCTION}\n\n" + P.TARGET_CWE_LINE.format(cwe_id=t["cwe_id"], cwe_name=entry["name"])


def direct_feedback_text(findings):
    lines = [P.DIRECT_FEEDBACK_HEADER]
    for f in findings:
        cwe_ids = f.get("cwe_ids") or ["unknown"]
        lines.append(P.DIRECT_FEEDBACK_ITEM.format(
            cwe_id=str(cwe_ids[0]).zfill(3), message=f["message"],
            start_line=f["start_line"], start_column=f["start_column"]))
    return "\n".join(lines)


def vulnerable_conversations(tasks, args):
    """Yield vanilla conversations whose code has CodeQL findings."""
    responses = load_responses_by_id(args.responses)
    index = read_json(args.index)                      # filename -> {"id", ...}
    issues = load_sarif(args.sarif, index)             # filename -> {"findings": [...]}
    file_of_id = {v["id"]: k for k, v in index.items()}
    for t in tasks:
        fname = file_of_id.get(t["id"])
        if fname is None or fname not in issues:
            continue
        findings = issues[fname]["findings"]
        if not findings:
            continue
        r = responses.get(t["id"])
        if r is None:
            continue
        yield t, r["messages"], r["response"], findings


def build(args):
    tasks = read_jsonl(args.input_file)
    catalog = load_cwe_catalog()
    out = []

    if args.task == "vanilla":
        for t in tasks:
            out.append({**t, "task_name": args.task,
                        "messages": [user(f"{base(t['task'])}\n\n{P.VANILLA_CODE_GEN_END}")]})

    elif args.task == "hint_generation":
        instr = P.VUL_HINTS_GENERATION.format(num_hints=args.num_hints)
        for t in tasks:
            out.append({**t, "task_name": args.task, "num_hints": args.num_hints,
                        "messages": [user(f"{base(t['task'])}\n\n{instr}")]})

    elif args.task == "code_gen_with_hints":
        hints = load_responses_by_id(args.hints)
        for t in tasks:
            h = hints.get(t["id"])
            if h is None:
                continue
            k = h.get("num_hints", args.num_hints)
            content = (f"{base(t['task'])}\n\n{P.CODE_GEN_WITH_HINTS_INSTRUCTION.format(num_hints=k)}\n"
                       f"{h['response'].strip()}\n\n{P.CODE_GEN_WITH_HINTS_END}")
            out.append({**t, "task_name": args.task, "hints": h["response"], "messages": [user(content)]})

    elif args.task in ("code_gen_with_cwe_definition", "directive_hint_generation", "code_gen_with_directive_hint"):
        directive = load_responses_by_id(args.directive_hints) if args.task == "code_gen_with_directive_hint" else {}
        for t in tasks:
            block = target_cwe_block(t, catalog)
            if block is None:
                continue
            if args.task == "code_gen_with_cwe_definition":
                content = f"{base(t['task'])}\n\n{block}\n\n{P.CODE_GEN_WITH_TARGET_CWE_END}"
                out.append({**t, "task_name": args.task, "messages": [user(content)]})
            elif args.task == "directive_hint_generation":
                content = f"{base(t['task'])}\n\n{block}\n\n{P.DIRECTIVE_HINT_GENERATION}"
                out.append({**t, "task_name": args.task, "messages": [user(content)]})
            else:
                d = directive.get(t["id"])
                if d is None:
                    continue
                content = f"{base(t['task'])}\n\n{block}\n{d['response'].strip()}\n\n{P.CODE_GEN_WITH_TARGET_CWE_END}"
                out.append({**t, "task_name": args.task, "directive_hint": d["response"], "messages": [user(content)]})

    elif args.task in ("explained_feedback_generation", "repair_direct"):
        end = P.EXPLAINED_FEEDBACK_GENERATION_END if args.task == "explained_feedback_generation" else P.REPAIR_END
        for t, msgs, resp, findings in vulnerable_conversations(tasks, args):
            fb = direct_feedback_text(findings)
            out.append({**t, "task_name": args.task, "direct_feedback": fb,
                        "messages": list(msgs) + [assistant(resp), user(f"{fb}\n{end}")]})

    elif args.task == "repair_explained":
        feedback = load_responses_by_id(args.feedback)
        for t, msgs, resp, findings in vulnerable_conversations(tasks, args):
            fbr = feedback.get(t["id"])
            if fbr is None:
                continue
            content = f"{P.DIRECT_FEEDBACK_HEADER}\n{fbr['response'].strip()}\n{P.REPAIR_END}"
            out.append({**t, "task_name": args.task, "explained_feedback": fbr["response"],
                        "messages": list(msgs) + [assistant(resp), user(content)]})

    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-t", "--task", required=True, choices=TASKS)
    ap.add_argument("-i", "--input_file", required=True, help="task file from prepare_datasets.py")
    ap.add_argument("-o", "--output_file", required=True)
    ap.add_argument("--num_hints", type=int, default=5, help="k for hint_generation (default 5)")
    ap.add_argument("--hints", help="responses.jsonl of a hint_generation run")
    ap.add_argument("--directive_hints", help="responses.jsonl of a directive_hint_generation run")
    ap.add_argument("--responses", help="responses.jsonl of the vanilla run being repaired")
    ap.add_argument("--index", help="index.json written by extract_code.py for the vanilla run")
    ap.add_argument("--sarif", help="CodeQL SARIF output for the vanilla run")
    ap.add_argument("--feedback", help="responses.jsonl of an explained_feedback_generation run")
    args = ap.parse_args()

    need = {
        "code_gen_with_hints": ["hints"],
        "code_gen_with_directive_hint": ["directive_hints"],
        "explained_feedback_generation": ["responses", "index", "sarif"],
        "repair_direct": ["responses", "index", "sarif"],
        "repair_explained": ["responses", "index", "sarif", "feedback"],
    }.get(args.task, [])
    missing = [n for n in need if getattr(args, n) is None]
    if missing:
        sys.exit(f"--{args.task} requires: " + ", ".join(f"--{m}" for m in missing))

    out = build(args)
    write_jsonl(out, args.output_file)
    print(f"{args.task}: {len(out)} prompts -> {args.output_file}")


if __name__ == "__main__":
    main()
