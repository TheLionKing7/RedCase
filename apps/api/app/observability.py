"""Prometheus observability (Task OBS) — counters + registry shared across the API.

This module owns the global Prometheus registry and per-function instrumented
counters. It is intentionally dependency-light (prometheus-client only) and
import-safe: importing it registers nothing beyond metric objects, so tests that
import it from any module do not require network access or secrets.

ZDR (HANDOFF.md 2.1): counters carry no document text, question bodies, or
tenant ids — only labels like ``reason`` (``citation_integrity``,
``insufficient_grounding``, ``provider_fallback``) and boolean flags. The
/metrics endpoint is deliberately UNauthenticated: Prometheus scrapes with a
bearer token; the route itself exposes only aggregate numeric counters.
"""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    generate_latest,
    registry,
)

# Registry is explicit so tests can reset it (REGISTRY is global and sticky).
REGISTRY = registry.CollectorRegistry()

# --- Query-outcome counters (refusals / fabrications) --------------------------
# ``reason`` mirrors the refusal reasons recorded in retrieval/service.py:
#   citation_integrity, insufficient_grounding, answer_timeout, provider_fallback.
ANSWER_REFUSALS = Counter(
    "redcase_answer_refusals_total",
    "Total grounded-answer refusals, by reason.",
    labelnames=("reason",),
    registry=REGISTRY,
)
ANSWER_TIMEOUTS = Counter(
    "redcase_answer_timeouts_total",
    "Total answer calls that overran the answer_timeout_s ceiling.",
    registry=REGISTRY,
)
FABRICATION_REFUSALS = Counter(
    "redcase_fabrication_refusals_total",
    "Total answers refused because a fabricated citation was detected.",
    registry=REGISTRY,
)
# Health gauges (0/1) exported so the Prometheus rule can be written against
# a real metric instead of a subnet. Set by /v1/health/detail.
HEALTH_DB = Gauge(
    "redcase_health_db",
    "Database readiness: 1 up, 0 down (from /v1/health/detail).",
    registry=REGISTRY,
)
HEALTH_PROVIDERS = Gauge(
    "redcase_health_providers",
    "Answer-provider chain readiness: 1 configured, 0 unconfigured.",
    registry=REGISTRY,
)
# --- Provider fallback chain ---------------------------------------------------
# Incremented every time the configured primary LLM is swapped for a fallback
# (make_llm returns a provider != the configured answer_model_primary, or an
# explicit fallback occurs). ``from_provider``/``to_provider`` keep the chain
# observable without logging bodies.
PROVIDER_FALLBACKS = Counter(
    "redcase_provider_fallbacks_total",
    "Total LLM provider fallback events, from -> to.",
    labelnames=("from_provider", "to_provider"),
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content-type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
