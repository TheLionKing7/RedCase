"""One-shot provider probe for the redirected battery plan (owner 2026-09-19).

Sends (a) a tiny call and (b) a realistic battery-size (~10k-token) call
to each candidate provider via the app's own client path, and reports
status/latency/error class. Answers the spend question BEFORE any battery
run: can this provider serve grounded legal prompts at all, and at what
size does it start rejecting?

Prints NO secrets and NO prompt bodies (sizes only) — ZDR.

Usage: python -m scripts.probe_providers [cerebras groq ...]
"""

import asyncio
import sys
import time

from app.config import get_settings
from app.retrieval.clients import _provider_client

TINY = "Reply with exactly: ok"
# ~10k tokens of filler — sizes the call like a real battery prompt
# (retrieval budget 8 passages + system + question) without any corpus text.
FILLER = "The quick brown fox jumps over the lazy dog. "
LARGE = (
    "Summarize the following passage in one sentence. " + FILLER * 1500
)


async def probe_one(name: str) -> None:
    settings = get_settings()
    llm = _provider_client(name, settings)
    if llm is None:
        print(f"{name}: NO CREDENTIAL provisioned", flush=True)
        return
    for label, prompt in (("tiny", TINY), ("~10k-token", LARGE)):
        t0 = time.monotonic()
        try:
            text = await llm.answer("You are a helpful assistant.", prompt)
            dt = time.monotonic() - t0
            print(
                f"{name} [{label}]: OK in {dt:.1f}s, {len(text)} chars back",
                flush=True,
            )
        except Exception as e:  # noqa: BLE001 — probe reports the class, never the body
            dt = time.monotonic() - t0
            detail = str(e)[:200]
            print(f"{name} [{label}]: FAIL in {dt:.1f}s — {type(e).__name__}: {detail}", flush=True)


async def main() -> None:
    names = sys.argv[1:] or ["cerebras", "groq"]
    for name in names:
        await probe_one(name)


if __name__ == "__main__":
    asyncio.run(main())
