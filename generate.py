"""Generate model responses for a prompt file."""
import argparse
import os

from common import read_jsonl, write_jsonl
from models import MAX_NEW_TOKENS, TEMPERATURE_BY_TASK, TOP_P, resolve


class HFGenerator:
    def __init__(self, model_id, dtype="bfloat16", trust_remote_code=False):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=trust_remote_code)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=getattr(torch, dtype), device_map="auto",
            trust_remote_code=trust_remote_code)
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    def __call__(self, messages, temperature, max_new_tokens):
        ids = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
        ids = ids.to(self.model.device)
        kwargs = dict(max_new_tokens=max_new_tokens, pad_token_id=self.tokenizer.pad_token_id)
        if temperature > 0:
            kwargs.update(do_sample=True, temperature=temperature, top_p=TOP_P)
        else:
            kwargs.update(do_sample=False)
        with self.torch.no_grad():
            out = self.model.generate(ids, **kwargs)
        return self.tokenizer.decode(out[0, ids.shape[1]:], skip_special_tokens=True)


class APIGenerator:
    def __init__(self, model_id):
        from llm_api import chat
        self.chat = chat
        self.model_id = model_id

    def __call__(self, messages, temperature, max_new_tokens):
        return self.chat(messages, self.model_id, temperature=temperature, max_tokens=max_new_tokens, top_p=TOP_P)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input_file", required=True)
    ap.add_argument("-o", "--output_file", required=True)
    ap.add_argument("-m", "--model", required=True, help="short name from models.py, a Hugging Face repo id, or an API model id")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--max_new_tokens", type=int, default=None)
    ap.add_argument("--dtype", default="bfloat16")
    ap.add_argument("--trust_remote_code", action="store_true", help="needed for DeepSeek-Coder-V2")
    ap.add_argument("--limit", type=int, default=None, help="process only the first N prompts")
    args = ap.parse_args()

    backend, model_id = resolve(args.model)
    prompts = read_jsonl(args.input_file)
    if args.limit:
        prompts = prompts[: args.limit]

    done = {}
    if os.path.exists(args.output_file):
        for r in read_jsonl(args.output_file):
            if r.get("response") is not None:
                done[r["id"]] = r
    print(f"{len(prompts)} prompts, {len(done)} already answered, model={model_id} ({backend})")

    if backend == "hf":
        gen = HFGenerator(model_id, dtype=args.dtype, trust_remote_code=args.trust_remote_code or "deepseek" in model_id.lower())
    else:
        gen = APIGenerator(model_id)
    max_new = args.max_new_tokens or MAX_NEW_TOKENS[backend]

    results = []
    for i, rec in enumerate(prompts, 1):
        if rec["id"] in done:
            results.append(done[rec["id"]])
            continue
        temp = args.temperature if args.temperature is not None else TEMPERATURE_BY_TASK.get(rec.get("task_name"), 0.0)
        response = gen(rec["messages"], temp, max_new)
        results.append({**rec, "response": response, "model": args.model})
        if i % 10 == 0 or i == len(prompts):
            write_jsonl(results, args.output_file)
            print(f"  [{i}/{len(prompts)}]")
    write_jsonl(results, args.output_file)
    print(f"done -> {args.output_file}")


if __name__ == "__main__":
    main()
