#!/usr/bin/env python3
"""Probe Experiential Labs (explabs) gateway for the best cheap coding model.

Usage:
    export EXPLABS_API_KEY
    python explabs_coding_probe.py                 # all candidates
    python explabs_coding_probe.py claude-sonnet-5 deepseek-v4-flash   # subset

What it measures, per model:
  - Task 1: bug fix against a failing test (auto-scored by executing the fix)
  - Task 2: implement-to-spec (auto-scored by running unit tests)
  - Task 3: strict-JSON tool-call discipline (instruction-following for agents)
  - Latency, tokens used, and estimated cost (from the catalog price table below)

Ranked output: quality first (tasks passed), then cost. Slugs are fuzzy-matched
against GET /v1/models, so catalog renames don't break the run.
"""
import json, os, re, sys, time, urllib.request

BASE = "https://api.experientiallabs.ai/v1"
KEY = os.environ.get("EXPLABS_API_KEY", "").strip()
if not KEY:
    print(
        "Missing EXPLABS_API_KEY. Set it before running this script:\n"
        "  PowerShell: $env:EXPLABS_API_KEY='your_key_here'\n"
        "  bash/zsh:  export EXPLABS_API_KEY='your_key_here'",
        file=sys.stderr,
    )
    raise SystemExit(1)

# Catalog prices ($/1M input, $/1M output) — from platform.experientiallabs.ai, Sept 2026
PRICES = {
    "claude-fable-5.1": (10.00, 50.00), "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00), "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4.5": (1.00, 5.00),
    "gpt-5.6-sol": (2.00, 10.00), "gpt-5.6-luna": (0.0, 0.0),
    "gemini-3.7-flash": (0.38, 1.88), "kimi-k3": (3.00, 12.75),
    "glm-5.3": (1.19, 4.40), "qwen3.8-27b": (0.16, 0.74),
    "deepseek-v4": (0.042, 0.085), "deepseek-v4-flash": (0.021, 0.042),
    "nemotron-3-ultra": (0.0, 0.0), "jev": (0.0, 0.0),
}
CANDIDATES = list(PRICES)

# ---------------- tasks ----------------

TASK1_BUG = '''You are given a buggy Python function and a failing test. Reply with ONLY a Python code block containing the corrected function (same name/signature). No explanation.

BUGGY:
def flatten(items):
    out = []
    for i in items:
        if isinstance(i, list):
            out.extend(flatten(i))
        else:
            out.append(i)
    return list(set(out))  # wrong: dedups and destroys order

TEST (must pass):
assert flatten([1, [2, [3, 2]], 4]) == [1, 2, 3, 4]
assert flatten([]) == []
'''

TASK2_IMPL = '''Implement the function below to specification. Reply with ONLY a Python code block. No explanation.

def lru_get(cache, order, key, compute, capacity):
    """LRU cache helper.
    cache: dict key->value. order: list of keys, most-recent LAST.
    On hit: move key to end of order, return cache[key].
    On miss: value = compute(key); store; append key to order;
             if len(order) > capacity: evict least-recently-used (front of order).
    Returns the value for key."""

TEST (must pass):
cache, order = {}, []
def c(k): return k * 10
assert lru_get(cache, order, "a", c, 2) == 10
assert lru_get(cache, order, "b", c, 2) == 20
assert lru_get(cache, order, "a", c, 2) == 10 and order == ["b", "a"]
assert lru_get(cache, order, "c", c, 2) == 30 and "b" not in cache and order == ["a", "c"]
'''

TASK3_JSON = '''You are a coding agent about to call a tool. Reply with ONLY a JSON object, no markdown, no prose, matching this schema:
{"tool": string, "args": {"path": string, "content": string}}
Context: create the file src/config.py with the single line: DEBUG = True
'''


def extract_code(text):
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def run_task(fn, arg):
    ns = {}
    try:
        exec(extract_code(arg), ns)
        fn(ns)
        return True
    except Exception as e:
        return f"FAIL: {type(e).__name__}: {e}"[:80]


def check_task1(ns):
    assert ns["flatten"]([1, [2, [3, 2]], 4]) == [1, 2, 3, 4]
    assert ns["flatten"]([]) == []


def check_task2(ns):
    cache, order = {}, {}
    cache, order = {}, []
    def c(k): return k * 10
    assert ns["lru_get"](cache, order, "a", c, 2) == 10
    assert ns["lru_get"](cache, order, "b", c, 2) == 20
    assert ns["lru_get"](cache, order, "a", c, 2) == 10 and order == ["b", "a"]
    assert ns["lru_get"](cache, order, "c", c, 2) == 30 and "b" not in cache


def check_task3(text):
    obj = json.loads(text.strip())
    assert obj["tool"] and obj["args"]["path"] == "src/config.py"
    assert "DEBUG = True" in obj["args"]["content"]


TASKS = [(TASK1_BUG, run_task, check_task1), (TASK2_IMPL, run_task, check_task2),
         (TASK3_JSON, lambda f, t: check_task3(t), None)]

# ---------------- gateway ----------------

def api(path, payload=None, method="GET"):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(payload).encode() if payload else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Experiential Labs HTTP {e.code} {e.reason} for {path}", file=sys.stderr)
        print(body[:2000], file=sys.stderr)
        raise


def chat(model, prompt, max_tokens=1200):
    t0 = time.time()
    r = api("/chat/completions", {"model": model, "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}]})
    dt = time.time() - t0
    u = r.get("usage", {})
    return r["choices"][0]["message"]["content"], dt, u


def resolve_slugs(wanted):
    avail = [m["id"] for m in api("/models")["data"]]
    resolved = {}
    for w in wanted:
        hits = [a for a in avail if w.lower().replace("-", "") in a.lower().replace("-", "")]
        resolved[w] = hits[0] if hits else None
    return resolved


def cost(usd_in, usd_out, u):
    return (u.get("prompt_tokens", 0) * usd_in + u.get("completion_tokens", 0) * usd_out) / 1e6


def main():
    wanted = sys.argv[1:] or CANDIDATES
    slugs = resolve_slugs(wanted)
    print(f"{'model':<26} {'t1':<3} {'t2':<3} {'t3':<3} {'lat':>6} {'tok':>6} {'est.$/1k':>9}  note")
    results = []
    for name in wanted:
        slug = slugs[name]
        pin, pout = PRICES.get(name, (None, None))
        if not slug:
            print(f"{name:<26}  -    -    -      -      -         -  NOT IN CATALOG")
            continue
        passed, total_tok, total_lat, note = 0, 0, 0.0, ""
        for i, (prompt, runner, checker) in enumerate(TASKS):
            try:
                out, dt, u = chat(slug, prompt)
                total_tok += u.get("total_tokens", 0); total_lat += dt
                ok = runner(checker, out) if checker else runner(None, out)
                if ok is True: passed += 1
                elif i < 2 and note == "": note = str(ok)
            except Exception as e:
                note = f"{type(e).__name__}"[:40]
                break
        c = cost(pin, pout, {"prompt_tokens": total_tok // 2, "completion_tokens": total_tok // 2}) if pin is not None else 0
        per1k = (c / total_tok * 1000) if total_tok else 0
        results.append((passed, per1k, name))
        marks = ["✓" if False else "?" for _ in range(3)]  # per-task detail shown via note
        print(f"{name:<26} {passed}/3  {total_lat:5.1f}s {total_tok:6d} {per1k:9.5f}  {note}")
    print("\nRanking (quality desc, then cost asc):")
    for p, c, n in sorted(results, key=lambda r: (-r[0], r[1])):
        print(f"  {p}/3  ${c:.5f}/1k-tok  {n}")


if __name__ == "__main__":
    main()
