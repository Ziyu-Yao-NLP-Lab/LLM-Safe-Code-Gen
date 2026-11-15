"""OpenAI / Azure OpenAI chat client."""
import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if os.getenv("AZURE_OPENAI_API_KEY"):
        from openai import AzureOpenAI
        _client = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        )
    elif os.getenv("OPENAI_API_KEY"):
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.getenv("OPENAI_BASE_URL"))
    else:
        raise RuntimeError("Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY (see .env.example).")
    return _client


def _deployment_name(model_id: str) -> str:
    key = "AZURE_DEPLOYMENT_" + re.sub(r"[^A-Za-z0-9]", "_", model_id).upper()
    return os.getenv(key, model_id)


def chat(messages, model_id, temperature=0.0, max_tokens=4096, top_p=1.0, retries=20):
    client = _get_client()
    name = _deployment_name(model_id) if os.getenv("AZURE_OPENAI_API_KEY") else model_id
    for attempt in range(retries):
        try:
            res = client.chat.completions.create(
                model=name, messages=messages, temperature=temperature,
                max_tokens=max_tokens, top_p=top_p, n=1,
            )
            return res.choices[0].message.content or ""
        except Exception as e:  # rate limits, transient errors
            wait = min(60, 3 * (attempt + 1))
            print(f"  API error ({e}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("API call failed after retries")
