# LLM-Safe-Code-Gen

Code for the paper **"Guiding AI to Fix Its Own Flaws: An Empirical Study on LLM-Driven Secure Code Generation"** (ACM Transactions on Software Engineering and Methodology, 2026).

The paper studies how large language models can be guided to write secure Python code. It measures how often models emit vulnerable code under plain prompts, then evaluates two mitigation paradigms: **proactive prevention**, where the model first lists the vulnerabilities it expects for a task and then implements the task while avoiding them, and **post-hoc repair**, where a static analyzer detects vulnerabilities in the generated code and the finding is fed back to the model at two levels of detail, the raw analyzer message or an explained version with remediation steps. Vulnerabilities are detected with CodeQL and reported as a target-vulnerability rate and an any-vulnerability rate. The study covers open-weight and proprietary models on three Python benchmarks.

This repository is a standalone implementation of that pipeline. Every step is one script with its own command-line interface, so any stage can be run on its own as long as its input files exist.

## 1. Requirements

- Python 3.10 or newer
- A GPU with about 80 GB of memory for the open-weight models in bfloat16 (smaller models fit on smaller GPUs)
- **CodeQL 2.19.1** (not included in this repository, see below)
- An OpenAI or Azure OpenAI API key for the proprietary models, for the explained-feedback generator, for the directive-hint generator, and for the hint-quality judge

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in the API key block you use
```

Gated Hugging Face models (Llama, CodeLlama) need `huggingface-cli login` or `HF_TOKEN` in `.env`.

### CodeQL

Install CodeQL yourself. The paper uses **CodeQL 2.19.1** with the `python-security-extended` query suite. Download the bundle for your platform from the [codeql-bundle-v2.19.1 release](https://github.com/github/codeql-action/releases/tag/codeql-bundle-v2.19.1). The bundle contains the CLI and the `codeql/python-queries` pack.

## 2. Data

| Benchmark | Where to get it | File expected by this repo |
|---|---|---|
| SecCodePLT | [Virtue-AI-HUB/SecCodePLT](https://huggingface.co/datasets/Virtue-AI-HUB/SecCodePLT) | `data/SecCodePLT/seccodeplt_src.json` (included: JSON list with flattened `task_description.*` fields) |
| SecurityEval | [s2e-lab/SecurityEval](https://github.com/s2e-lab/SecurityEval) | `data/SecurityEval/securityeval_dataset.json` (included) |
| CyberSecEval (instruct) | [meta-llama/PurpleLlama](https://github.com/meta-llama/PurpleLlama), `CybersecurityBenchmarks/datasets/instruct/instruct.json` | `data/CyberSecEval/instruct.json` (download; the Python subset is selected automatically) |

`data/cwe_official/` holds the official CWE names and definitions (`all_cwe.json`, from the [CWE research view 1000](https://cwe.mitre.org/data/definitions/1000.html)) and `codeql_python_security_extended_cwes.json`, the CWE ids the `python-security-extended` suite can report.

Convert each benchmark into the common task format. Tasks whose target CWE the suite cannot report are dropped for SecCodePLT and CyberSecEval (pass `--covered_cwes <file>` to use a different list, or `--keep_uncovered` to keep every task):

```bash
python prepare_datasets.py -d seccodeplt   -i data/SecCodePLT/seccodeplt_src.json         -o data/tasks/seccodeplt.jsonl
python prepare_datasets.py -d securityeval -i data/SecurityEval/securityeval_dataset.json -o data/tasks/securityeval.jsonl
python prepare_datasets.py -d cyberseceval -i data/CyberSecEval/instruct.json             -o data/tasks/cyberseceval.jsonl
```

Each task record is `{"id", "dataset", "cwe_id", "task"}`. For SecCodePLT the task text is assembled from the description, function definition, context, arguments, return and raise fields; for the other two benchmarks the benchmark prompt is used as is.

## 3. Pipeline

```
prepare_datasets.py ──> tasks.jsonl
                            │
                build_prompts.py -t <condition>  ──> prompts.jsonl
                            │
                      generate.py -m <model>     ──> responses.jsonl
                            │
                      extract_code.py            ──> code/*.py + index.json
                            │
                      codeql (you run it)        ──> codeql/results.sarif
                            │
                      compute_metrics.py         ──> metrics.json  (TarV-R, AllV-R)
```

| Script | Purpose |
|---|---|
| `prepare_datasets.py` | Benchmark release to common task format |
| `build_prompts.py` | Chat prompts for one condition (vanilla, hints, target-CWE hints, repair) |
| `generate.py` | Runs prompts through an open-weight model (transformers) or an API model |
| `extract_code.py` | Pulls the Python code out of each response into one file per task |
| `compute_metrics.py` | TarV-R and AllV-R, per CWE, with optional breakdowns |
| `judge_hints.py` | Relevance and preciseness labels for self-generated hints |
| `prompts.py` | All prompt templates |
| `models.py` | Model registry and decoding settings |

Model short names (`-m`): `codellama-7b`, `codellama-34b`, `llama-3.1-8b`, `llama-3.2-3b`, `starcoder2-15b`, `deepseek-coder-v2`, `gpt-3.5-turbo`, `gpt-4o`. Any other Hugging Face repo id or API model id is accepted too.

Decoding settings are fixed in `models.py`: temperature 0.0 (greedy) for code generation and repair, 0.7 for hint, directive-hint and explained-feedback generation, 0.0 for the judge; top-p 1.0; 2,048 new tokens for open-weight models (bfloat16, no quantization) and 4,096 for API models. `generate.py` picks the temperature from the prompt's condition unless `--temperature` is given.

The commands below use SecCodePLT and GPT-4o as the running example. Replace the task file and model name for the other benchmarks and models. Output directories are a suggestion; every script takes explicit paths.

## 4. Vulnerable code generation with vanilla prompts

```bash
python build_prompts.py -t vanilla -i data/tasks/seccodeplt.jsonl -o runs/seccodeplt/vanilla/prompts.jsonl
python generate.py -i runs/seccodeplt/vanilla/prompts.jsonl -o runs/seccodeplt/vanilla/gpt-4o/responses.jsonl -m gpt-4o
python extract_code.py -i runs/seccodeplt/vanilla/gpt-4o/responses.jsonl -o runs/seccodeplt/vanilla/gpt-4o/code
codeql database create runs/seccodeplt/vanilla/gpt-4o/codeql/db --language=python --overwrite \
    --source-root=runs/seccodeplt/vanilla/gpt-4o/code
codeql database analyze runs/seccodeplt/vanilla/gpt-4o/codeql/db \
    codeql/python-queries:codeql-suites/python-security-extended.qls \
    --format=sarifv2.1.0 --output=runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif
python compute_metrics.py --tasks data/tasks/seccodeplt.jsonl \
    --index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    -o runs/seccodeplt/vanilla/gpt-4o/metrics.json
```

`metrics.json` reports the overall and per-CWE TarV-R and AllV-R. By default the denominator is the number of samples with an analysed file; `--denominator all` counts every task and treats samples without extractable code as not vulnerable.

## 5. Proactive prevention with self-generated vulnerability hints

Step 1, the model lists its top-k vulnerability hints for each task (k = 5 by default):

```bash
python build_prompts.py -t hint_generation --num_hints 5 -i data/tasks/seccodeplt.jsonl -o runs/seccodeplt/hints_k5/prompts.jsonl
python generate.py -i runs/seccodeplt/hints_k5/prompts.jsonl -o runs/seccodeplt/hints_k5/gpt-4o/responses.jsonl -m gpt-4o
```

Step 2, the same model implements the task with its own hints in the prompt, then the code is analysed exactly as in Section 4:

```bash
python build_prompts.py -t code_gen_with_hints -i data/tasks/seccodeplt.jsonl \
    --hints runs/seccodeplt/hints_k5/gpt-4o/responses.jsonl -o runs/seccodeplt/code_with_hints_k5/gpt-4o/prompts.jsonl
python generate.py -i runs/seccodeplt/code_with_hints_k5/gpt-4o/prompts.jsonl -o runs/seccodeplt/code_with_hints_k5/gpt-4o/responses.jsonl -m gpt-4o
python extract_code.py -i runs/seccodeplt/code_with_hints_k5/gpt-4o/responses.jsonl -o runs/seccodeplt/code_with_hints_k5/gpt-4o/code
codeql database create runs/seccodeplt/code_with_hints_k5/gpt-4o/codeql/db --language=python --overwrite \
    --source-root=runs/seccodeplt/code_with_hints_k5/gpt-4o/code
codeql database analyze runs/seccodeplt/code_with_hints_k5/gpt-4o/codeql/db \
    codeql/python-queries:codeql-suites/python-security-extended.qls \
    --format=sarifv2.1.0 --output=runs/seccodeplt/code_with_hints_k5/gpt-4o/codeql/results.sarif
python compute_metrics.py --tasks data/tasks/seccodeplt.jsonl \
    --index runs/seccodeplt/code_with_hints_k5/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/code_with_hints_k5/gpt-4o/codeql/results.sarif \
    --baseline_index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --baseline_sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    -o runs/seccodeplt/code_with_hints_k5/gpt-4o/metrics.json
```

`--baseline_*` evaluates the vanilla run on the same samples so the two rates are directly comparable.

### 5.1 Hint quality: relevance and preciseness

The judge (GPT-4o by default, temperature 0) checks whether any hint names the task's target CWE and, if so, whether its description matches the official CWE definition. Each sample is labelled `irrelevant`, `relevant` or `relevant_precise` (`unjudged` if its CWE is missing from `all_cwe.json`):

```bash
python judge_hints.py -i runs/seccodeplt/hints_k5/gpt-4o/responses.jsonl -o runs/seccodeplt/hints_k5/gpt-4o/labels.jsonl --judge gpt-4o
python compute_metrics.py --tasks data/tasks/seccodeplt.jsonl \
    --index runs/seccodeplt/code_with_hints_k5/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/code_with_hints_k5/gpt-4o/codeql/results.sarif \
    --baseline_index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --baseline_sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    --labels runs/seccodeplt/hints_k5/gpt-4o/labels.jsonl \
    -o runs/seccodeplt/code_with_hints_k5/gpt-4o/metrics_by_hint_quality.json
```

### 5.2 Hint style: CWE definition vs. directive hint

Both conditions hand the model the true target CWE. The definition condition adds only `CWE-ID: official name`. The directive condition adds an explanation, written by a separate model, of how that weakness can arise in the given task:

```bash
# CWE definition only
python build_prompts.py -t code_gen_with_cwe_definition -i data/tasks/seccodeplt.jsonl -o runs/seccodeplt/cwe_definition/prompts.jsonl
python generate.py -i runs/seccodeplt/cwe_definition/prompts.jsonl -o runs/seccodeplt/cwe_definition/gpt-4o/responses.jsonl -m gpt-4o

# Directive hint: generate the explanation once with gpt-4o, then reuse it for every evaluated model
python build_prompts.py -t directive_hint_generation -i data/tasks/seccodeplt.jsonl -o runs/seccodeplt/directive_hints/prompts.jsonl
python generate.py -i runs/seccodeplt/directive_hints/prompts.jsonl -o runs/seccodeplt/directive_hints/gpt-4o/responses.jsonl -m gpt-4o
python build_prompts.py -t code_gen_with_directive_hint -i data/tasks/seccodeplt.jsonl \
    --directive_hints runs/seccodeplt/directive_hints/gpt-4o/responses.jsonl -o runs/seccodeplt/directive/prompts.jsonl
python generate.py -i runs/seccodeplt/directive/prompts.jsonl -o runs/seccodeplt/directive/gpt-4o/responses.jsonl -m gpt-4o
```

Analyse each run with `extract_code.py`, CodeQL and `compute_metrics.py` as in Section 4.

### 5.3 Number of hints

Repeat Section 5 with `--num_hints k` for the values of k to compare. The `num_hints` value is stored in each hint record and reused automatically when the code-generation prompt is built.

## 6. Post-hoc repair with detector feedback

Repair starts from a vanilla run (Section 4) and covers the samples whose code has at least one CodeQL finding. The conversation is: vanilla prompt, the model's vulnerable code, then a feedback turn.

**Direct feedback**: the raw CodeQL findings, one line per finding with CWE id, message, line and column.

```bash
python build_prompts.py -t repair_direct -i data/tasks/seccodeplt.jsonl \
    --responses runs/seccodeplt/vanilla/gpt-4o/responses.jsonl \
    --index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    -o runs/seccodeplt/repair_direct/gpt-4o/prompts.jsonl
python generate.py -i runs/seccodeplt/repair_direct/gpt-4o/prompts.jsonl -o runs/seccodeplt/repair_direct/gpt-4o/responses.jsonl -m gpt-4o
```

**Explained feedback**: an explainer model rewrites the direct feedback into an explanation of why each finding is a vulnerability and how to fix it. Generate the explanation with `gpt-4o` for the teacher-explained condition, or with the evaluated model itself for the self-explained condition:

```bash
python build_prompts.py -t explained_feedback_generation -i data/tasks/seccodeplt.jsonl \
    --responses runs/seccodeplt/vanilla/gpt-4o/responses.jsonl \
    --index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    -o runs/seccodeplt/explained_feedback/gpt-4o/prompts.jsonl
python generate.py -i runs/seccodeplt/explained_feedback/gpt-4o/prompts.jsonl -o runs/seccodeplt/explained_feedback/gpt-4o/responses.jsonl -m gpt-4o

python build_prompts.py -t repair_explained -i data/tasks/seccodeplt.jsonl \
    --responses runs/seccodeplt/vanilla/gpt-4o/responses.jsonl \
    --index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    --feedback runs/seccodeplt/explained_feedback/gpt-4o/responses.jsonl \
    -o runs/seccodeplt/repair_explained/gpt-4o/prompts.jsonl
python generate.py -i runs/seccodeplt/repair_explained/gpt-4o/prompts.jsonl -o runs/seccodeplt/repair_explained/gpt-4o/responses.jsonl -m gpt-4o
```

Analyse the repaired code with `extract_code.py` and CodeQL, then compute the post-repair rates over the full sample set by falling back to the vanilla result for samples that were not repaired:

```bash
python extract_code.py -i runs/seccodeplt/repair_direct/gpt-4o/responses.jsonl -o runs/seccodeplt/repair_direct/gpt-4o/code
codeql database create runs/seccodeplt/repair_direct/gpt-4o/codeql/db --language=python --overwrite \
    --source-root=runs/seccodeplt/repair_direct/gpt-4o/code
codeql database analyze runs/seccodeplt/repair_direct/gpt-4o/codeql/db \
    codeql/python-queries:codeql-suites/python-security-extended.qls \
    --format=sarifv2.1.0 --output=runs/seccodeplt/repair_direct/gpt-4o/codeql/results.sarif
python compute_metrics.py --tasks data/tasks/seccodeplt.jsonl \
    --index runs/seccodeplt/repair_direct/gpt-4o/code/index.json \
    --sarif runs/seccodeplt/repair_direct/gpt-4o/codeql/results.sarif \
    --fallback_index runs/seccodeplt/vanilla/gpt-4o/code/index.json \
    --fallback_sarif runs/seccodeplt/vanilla/gpt-4o/codeql/results.sarif \
    -o runs/seccodeplt/repair_direct/gpt-4o/metrics.json
```

## 7. Citation

```bibtex
@article{yan2026guiding,
  title   = {Guiding AI to Fix Its Own Flaws: An Empirical Study on LLM-Driven Secure Code Generation},
  author  = {Yan, Hao and Vaidya, Swapneel Suhas and Zhang, Xiaokuan and Yao, Ziyu},
  journal = {ACM Transactions on Software Engineering and Methodology},
  year    = {2026}
}
```
