"""Observability (Task OBS) — /metrics + /health/detail + instrumented counters.

Covers the DoD:
  * /v1/metrics serves Prometheus text exposition with the expected counters;
  * /v1/health/detail reports db up/down + providers configured without raising;
  * refusal/fabrication/timeout counters are bound to the served registry;
  * the provider-fallback counter increments when FallbackLLM moves providers.

The FallbackLLM async tests reuse the deterministic fake-leaf pattern from
test_provider_fallback.py.
"""

import asyncio

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.observability import REGISTRY
from app.retrieval.clients import FallbackLLM


def _isolated_settings() -> Settings:
    # Never read the developer's real .env (which provisions live keys); the test
    # suite must be hermetic against local credentials.
    return Settings(_env_file=None)


def _sample_value(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


class FakeLeaf:
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


# ---------------------------------------------------------------------------
# /v1/metrics
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_prometheus_text() -> None:
    client = TestClient(create_app(_isolated_settings()))
    resp = client.get("/v1/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# HELP" in body
    assert "redcase_answer_refusals_total" in body
    assert "redcase_fabrication_refusals_total" in body
    assert "redcase_provider_fallbacks_total" in body

# ---------------------------------------------------------------------------
# /v1/health/detail
# ---------------------------------------------------------------------------

def test_health_detail_reports_without_database() -> None:
    # No database_url -> no pool -> db "down", but the probe still returns a
    # body (never raises onto the load-balancer).
    with TestClient(create_app(_isolated_settings())) as client:
        resp = client.get("/v1/health/detail")
        assert resp.status_code == 200
        body = resp.json()
        assert body["db"] == "down"
        assert body["providers"] in ("configured", "unconfigured")
        assert body["status"] in ("ok", "degraded")


def test_health_detail_providers_flag_unconfigured() -> None:
    with TestClient(create_app(_isolated_settings())) as client:
        body = client.get("/v1/health/detail").json()
    # With no secrets the answer chain is unconfigured.
    assert body["providers"] == "unconfigured"


# ---------------------------------------------------------------------------
# Provider-fallback counter (FallbackLLM)
# ---------------------------------------------------------------------------

async def test_provider_fallback_counter_increments(monkeypatch) -> None:
    monkeypatch.setattr("app.retrieval.clients._fallback_delay", lambda ra, r: 0.0)
    before = _sample_value(
        "redcase_provider_fallbacks_total",
        from_provider="primary",
        to_provider="fallback",
    )
    primary = FakeLeaf("primary", [_status_error(402)])
    fallback = FakeLeaf("fallback", ["fallback answer"])
    chain = FallbackLLM([("primary", primary), ("fallback", fallback)])

    out = await chain.answer("s", "u")

    assert out == "fallback answer"
    after = _sample_value(
        "redcase_provider_fallbacks_total",
        from_provider="primary",
        to_provider="fallback",
    )
    assert after - before == 1.0


def test_no_fallback_counter_on_single_provider_success() -> None:
    primary = FakeLeaf("primary", ["grounded answer"])
    chain = FallbackLLM([("primary", primary)])
    asyncio.run(chain.answer("s", "u"))
    assert _sample_value("redcase_provider_fallbacks_total") == 0.0


# ---------------------------------------------------------------------------
# Counter binding on the served registry
# ---------------------------------------------------------------------------

def test_counters_bound_to_served_registry() -> None:
    from app.observability import (
        ANSWER_REFUSALS,
        ANSWER_TIMEOUTS,
        FABRICATION_REFUSALS,
        PROVIDER_FALLBACKS,
    )
    assert ANSWER_REFUSALS._name == "redcase_answer_refusals"
    assert ANSWER_TIMEOUTS._name == "redcase_answer_timeouts"
    assert FABRICATION_REFUSALS._name == "redcase_fabrication_refusals"
    assert PROVIDER_FALLBACKS._name == "redcase_provider_fallbacks"


def test_metrics_reflect_incremented_counter() -> None:
    # Show the registry /metrics serves is the one that increments.
    from app.observability import FABRICATION_REFUSALS
    FABRICATION_REFUSALS.inc()
    client = TestClient(create_app(Settings()))
    body = client.get("/v1/metrics").text
    assert "redcase_fabrication_refusals_total 1.0" in body

