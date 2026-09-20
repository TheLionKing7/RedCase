"""make_llm two-tier provider error policy (Task 2.6) — pure unit tests.

No live providers, no DB: the FallbackLLM is exercised with deterministic fake
leaf clients. The three properties under test keep the under-refusal guard and
provider-comparison evidence honest:

  * a 429 retries the SAME provider before any fallback;
  * a hard failure / exhausted quota (402) falls through and the audit names
    the actual server (FallbackLLM.provider, persisted by write_audit);
  * a content refusal is a normal answer — exactly one leaf call, no retry,
    no fallback (the day fallback leaks into the refusal path is the day the
    under-refusal guard gets a hole).
"""

from app.middleware.audit import write_audit
from app.retrieval.clients import FallbackLLM, RateLimitedError


class FakeLeaf:
    """Deterministic leaf client: pops one response per answer() call, raising
    it if it's an Exception and returning it otherwise."""

    def __init__(self, provider, responses):
        self.provider = provider
        self.model = f"{provider}-model"
        self._responses = list(responses)
        self.calls = 0

    async def answer(self, system, user):
        self.calls += 1
        r = self._responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _status_error(status_code: int) -> Exception:
    err = RuntimeError(f"HTTP {status_code}")
    err.status_code = status_code  # type: ignore[attr-defined]
    return err


async def test_429_then_success_stays_on_same_provider(monkeypatch):
    monkeypatch.setattr("app.retrieval.clients._fallback_delay", lambda ra, r: 0.0)
    primary = FakeLeaf(
        "primary",
        [
            RateLimitedError(None, "primary", "primary-model"),
            RateLimitedError(None, "primary", "primary-model"),
            "grounded answer",
        ],
    )
    fallback = FakeLeaf("fallback", ["fallback answer"])
    chain = FallbackLLM([("primary", primary), ("fallback", fallback)])

    out = await chain.answer("s", "u")

    assert out == "grounded answer"
    assert chain.provider == "primary"  # never fell back
    assert chain.model == "primary-model"
    assert primary.calls == 3  # 2x 429 + 1 success
    assert fallback.calls == 0


async def test_hard_failure_falls_through_and_audit_names_fallback():
    primary = FakeLeaf("primary", [_status_error(402)])
    fallback = FakeLeaf("fallback", ["fallback answer"])
    chain = FallbackLLM([("primary", primary), ("fallback", fallback)])

    out = await chain.answer("s", "u")

    assert out == "fallback answer"
    assert chain.provider == "fallback"  # query_audit will record this
    assert chain.model == "fallback-model"
    assert primary.calls == 1
    assert fallback.calls == 1


async def test_content_refusal_makes_one_call_no_fallback():
    primary = FakeLeaf("primary", ["No binding precedent found in Vault B."])
    fallback = FakeLeaf("fallback", ["fallback answer"])
    chain = FallbackLLM([("primary", primary), ("fallback", fallback)])

    out = await chain.answer("s", "u")

    assert out == "No binding precedent found in Vault B."
    assert primary.calls == 1  # exactly one call
    assert fallback.calls == 0  # no fallback — a refusal is not an error


class FakeConn:
    def __init__(self):
        self.executed = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


async def test_write_audit_persists_serving_provider():
    conn = FakeConn()
    await write_audit(conn, {
        "tenant_id": "a0000001-0000-4000-8000-000000000001",
        "user_ref": "user-1",
        "question_hash": "abc",
        "serving_provider": "explabs",
        "serving_model": "claude-sonnet-4.5",
    })
    _, args = conn.executed[0]
    assert args[-2] == "explabs"
    assert args[-1] == "claude-sonnet-4.5"


async def test_write_audit_serving_provider_defaults_none():
    conn = FakeConn()
    await write_audit(conn, {
        "tenant_id": "a0000001-0000-4000-8000-000000000001",
        "user_ref": "user-1",
        "question_hash": "abc",
    })
    _, args = conn.executed[0]
    assert args[-2] is None
    assert args[-1] is None
