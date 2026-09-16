"""One-off probe: which embedding providers actually work right now.

Prints status codes and embedding dimensions only. Never prints secrets.
Run: .venv/Scripts/python.exe probe_keys.py
"""

import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

FAIL = "\033[31mFAIL\033[0m"
OK = "\033[32mOK\033[0m"


def report(name: str, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - probe must not crash
        print(f"[{FAIL}] {name}: {type(exc).__name__}: {exc}")


def probe_openrouter():
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        print("[--] OpenRouter: no key in .env")
        return
    r = httpx.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "openai/text-embedding-3-large", "input": "hello"},
        timeout=60,
    )
    print(f"[{OK if r.status_code == 200 else FAIL}] OpenRouter "
          f"text-embedding-3-large: HTTP {r.status_code}")
    if r.status_code == 200:
        dims = len(r.json()["data"][0]["embedding"])
        print(f"       dimensions: {dims}")


def probe_hf(model: str, extra: dict | None = None):
    key = os.environ.get("HUGGINGFACE_API_KEY", "")
    if not key:
        print("[--] HuggingFace: no key in .env")
        return
    payload = {"model": model, "input": "hello"}
    if extra:
        payload.update(extra)
    r = httpx.post(
        "https://router.huggingface.co/v1/embeddings",
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=120,
    )
    status = OK if r.status_code == 200 else FAIL
    print(f"[{status}] HF {model} {extra or ''}: HTTP {r.status_code}")
    if r.status_code != 200:
        body = r.text[:300]
        print(f"       {body}")
        return
    dims = len(r.json()["data"][0]["embedding"])
    print(f"       dimensions: {dims}")


print("=== embedding provider probe ===")
report("OpenRouter", probe_openrouter)
report("HF Qwen3-Embedding-8B (default)", lambda: probe_hf("Qwen/Qwen3-Embedding-8B"))
report("HF Qwen3-Embedding-8B (dimensions=3072)",
       lambda: probe_hf("Qwen/Qwen3-Embedding-8B", {"dimensions": 3072}))
sys.exit(0)
