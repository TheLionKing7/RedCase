#!/usr/bin/env python3
"""Probe Experiential Labs catalog for the best RedCase ANSWER model.

The answer role has different gates than coding: (1) strict refusal when
passages don't support an answer, (2) refusal even when TANGENTIAL passages
are provided (the B17-class discriminator), (3) citation-format compliance,
(4) latency. A model that answers task 2 or task 3 is disqualified regardless
of quality elsewhere.

Usage:
    setx EXPLABS_API_KEY xpl_...   (Windows: new terminal after)
    python explabs_answer_probe.py                       # all candidates
    python explabs_answer_probe.py claude-sonnet-5 deepseek-v4 gpt-oss-120b
"""
import json, os, re, sys, time, urllib.request

BASE = "https://api.experientiallabs.ai/v1"
KEY = os.environ["EXPLABS_API_KEY"]

# Catalog prices ($/1M in, out) — platform.experientiallabs.ai, Sept 2026
PRICES = {
    "claude-fable-5.1": (10.0, 50.0), "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4.5": (1.0, 5.0),
    "gpt-5.6-sol": (2.0, 10.0), "gpt-5.6-luna": (0.0, 0.0),
    "gemini-3.7-flash": (0.38, 1.88), "kimi-k3": (3.0, 12.75),
    "glm-5.3": (1.19, 4.40), "qwen3.8-27b": (0.16, 0.74),
    "deepseek-v4": (0.042, 0.085), "deepseek-v4-flash": (0.021, 0.042),
    "nemotron-3-ultra": (0.0, 0.0), "gpt-oss-120b": (0.30, 0.90),
    "jev": (0.0, 0.0),
}
CANDIDATES = list(PRICES)

REFUSAL = "No binding precedent found in Vault B."

GROUNDED_SYSTEM = """You are a legal research engine restricted to the passages below.
Rules: (1) use ONLY the passages; (2) every proposition needs a citation in the
form [B:source, p.X]; (3) if the passages do not support an answer, output
exactly: "No binding precedent found in Vault B."; (4) never invent cases or pages."""

PASSAGES_OK = """<passages>
[B:madukolu, pp.341-343] A court is competent when (1) it is properly constituted...
[B:madukolu, pp.341-343] The condition precedent of jurisdiction: proper parties, subject matter, and relief...
</passages>
Question: What conditions make a Nigerian court competent to hear a case?"""

PASSAGES_TANGENTIAL = """<passages>
[B:adesanya, pp.12-14] The plaintiff challenged the Act on the ground that he had not been afforded a fair hearing...
[B:abacha, pp.710-712] The African Charter is domesticated in Nigeria by Cap A9...
</passages>
Question: What is the procedure for obtaining an interim injunction in Nigeria?"""

QUESTION_BARE = "What is the procedure for obtaining an interim injunction in Nigeria?"

JSON_SYSTEM = 'Reply with ONLY a JSON object, no prose: {"case": string, "citation": string, "page": string}'


def api(path, payload=None):
    req = urllib.request.Request(BASE + path,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
        data=json.dumps(payload).encode() if payload else None)
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def chat(model, system, user, max_tokens=900):
    t0 = time.time()
    r = api("/chat/completions", {"model": model, "temperature": 0, "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}]})
    u = r.get("usage", {})
    return r["choices"][0]["message"]["content"].strip(), time.time() - t0, u


def judge(name, slug):
    res = {"name": name, "disqualified": False}
    tok = lat = 0
    # T1: grounded answer with citations
    try:
        out, dt, u = chat(slug, GROUNDED_SYSTEM, PASSAGES_OK); lat += dt; tok += u.get("total_tokens", 0)
        res["t1_answered"] = REFUSAL not in out
        res["t1_cite_fmt"] = bool(re.search(r"\[B:[\w-]+,\s*p\.\d+\]", out))
    except Exception as e:
        return {"name": name, "error": f"T1 {type(e).__name__}"}
    # T2: out-of-corpus MUST refuse
    try:
        out, dt, u = chat(slug, GROUNDED_SYSTEM, QUESTION_BARE); lat += dt; tok += u.get("total_tokens", 0)
        res["t2_refused"] = REFUSAL in out
        if not res["t2_refused"]: res["disqualified"] = True
    except Exception as e:
        return {"name": name, "error": f"T2 {type(e).__name__}"}
    # T3: tangential passages MUST refuse (B17-class discriminator)
    try:
        out, dt, u = chat(slug, GROUNDED_SYSTEM, PASSAGES_TANGENTIAL); lat += dt; tok += u.get("total_tokens", 0)
        res["t3_refused_tangential"] = REFUSAL in out
        if not res["t3_refused_tangential"]: res["disqualified"] = True
    except Exception as e:
        return {"name": name, "error": f"T3 {type(e).__name__}"}
    # T4: JSON discipline (assistant tool-calling proxy)
    try:
        out, dt, u = chat(slug, JSON_SYSTEM,
            "Extract from: The court in Amaechi v. INEC (2008) 5 NWLR (Pt 1080) 227 at page 312 held so.",
            200); lat += dt; tok += u.get("total_tokens", 0)
        o = json.loads(out); res["t4_json"] = bool(o.get("case") and o.get("citation"))
    except Exception:
        res["t4_json"] = False
    pin, pout = PRICES.get(name, (0, 0))
    res["cost"] = (tok / 2 * pin + tok / 2 * pout) / 1e6
    res["lat"] = lat
    res["passed"] = (res.get("t2_refused") and res.get("t3_refused_tangential")
                     and res.get("t1_answered") and res.get("t1_cite_fmt"))
    return res


def main():
    wanted = sys.argv[1:] or CANDIDATES
    avail = [m["id"] for m in api("/models")["data"]]
    rows = []
    for name in wanted:
        hits = [a for a in avail if name.lower().replace("-", "") in a.lower().replace("-", "")]
        if not hits:
            print(f"{name:<22} NOT IN CATALOG"); continue
        r = judge(name, hits[0])
        if "error" in r:
            print(f"{name:<22} ERROR {r['error']}"); continue
        rows.append(r)
        flag = "PASS " if r["passed"] else ("DISQ " if r["disqualified"] else "PART ")
        print(f"{name:<22} {flag} t1:{str(r['t1_answered'])}/{str(r['t1_cite_fmt'])} "
              f"t2:{r['t2_refused']} t3:{r['t3_refused_tangential']} json:{r['t4_json']} "
              f"{r['lat']:5.1f}s ${r['cost']:.5f}")
    print("\n=== ELIGIBLE (passed all gates), ranked by cost ===")
    for r in sorted([x for x in rows if x["passed"]], key=lambda x: x["cost"]):
        print(f"  {r['name']:<22} ${r['cost']:.5f}/run  {r['lat']:.1f}s total")


if __name__ == "__main__":
    main()
