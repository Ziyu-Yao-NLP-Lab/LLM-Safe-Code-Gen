"""Model registry and decoding settings."""

MODELS = {
    # short name            backend    identifier
    "codellama-7b":        ("hf",  "codellama/CodeLlama-7b-Instruct-hf"),
    "codellama-34b":       ("hf",  "codellama/CodeLlama-34b-Instruct-hf"),
    "llama-3.1-8b":        ("hf",  "meta-llama/Llama-3.1-8B-Instruct"),
    "llama-3.2-3b":        ("hf",  "meta-llama/Llama-3.2-3B-Instruct"),
    "starcoder2-15b":      ("hf",  "bigcode/starcoder2-15b-instruct-v0.1"),
    "deepseek-coder-v2":   ("hf",  "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"),
    "gpt-3.5-turbo":       ("api", "gpt-3.5-turbo-0125"),
    "gpt-4o":              ("api", "gpt-4o-2024-05-13"),
}

TOP_P = 1.0
MAX_NEW_TOKENS = {"hf": 2048, "api": 4096}

TEMPERATURE_BY_TASK = {
    # code generation and repair: greedy
    "vanilla": 0.0,
    "code_gen_with_hints": 0.0,
    "code_gen_with_cwe_definition": 0.0,
    "code_gen_with_directive_hint": 0.0,
    "repair_direct": 0.0,
    "repair_explained": 0.0,
    # open-ended text generation
    "hint_generation": 0.7,
    "directive_hint_generation": 0.7,
    "explained_feedback_generation": 0.7,
    # judging
    "judge": 0.0,
}


def resolve(model_name: str):
    if model_name in MODELS:
        return MODELS[model_name]
    if model_name.startswith("gpt") or model_name.startswith("o1") or model_name.startswith("o3"):
        return "api", model_name
    return "hf", model_name
