# Alert Rules (Task OBS) — Prometheus /metrics + /health/detail

Consumes the observability surface added in Task OBS. Two scrape targets:

- `/v1/metrics` (Prometheus text exposition, bearer-token protected at ingress)
- `/v1/health/detail` (liveness + readiness probe for load balancer / uptime)

ZDR (HANDOFF.md 2.1): metrics expose **counters only** — no question bodies,
document text, or tenant ids. Alert labels carry reason strings
(`citation_integrity`, `insufficient_grounding`, `answer_timeout`) and
provider names, never content.

## Exposed metrics

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `redcase_answer_refusals_total` | Counter | `reason` | Grounded-answer refusals, per reason (`citation_integrity`, `insufficient_grounding`, `answer_timeout`). |
| `redcase_answer_timeouts_total` | Counter | — | Answer calls that overran `answer_timeout_s`. |
| `redcase_fabrication_refusals_total` | Counter | — | Answers refused because a fabricated citation was detected (§3.4 integrity gate). Hard safety gate — never amendable. |
| `redcase_provider_fallbacks_total` | Counter | `from_provider`, `to_provider` | Times the answer chain fell back from one provider to another. |
| `redcase_health_db` | Gauge | — | 1 when `/v1/health/detail` last ran `SELECT 1`; 0 when down. |
| `redcase_health_providers` | Gauge | — | 1 when an answer-provider credential is provisioned; 0 otherwise. |

## Alerting rules (Prometheus rule YAML)

```yaml
groups:
  - name: redcase-observability
    rules:
      # Hard safety gate: a fabricated citation must NEVER surface to a user.
      # This is a zero-tolerance gate, not a threshold — any breach pages.
      - alert: RedCaseCitationFabricationRefused
        expr: increase(redcase_fabrication_refusals_total[5m]) > 0
        for: 0m
        labels:
          severity: page
          jira: SEC
        annotations:
          summary: "A fabricated citation was detected and refused in the last 5m."

      # Sustained refusal rate signals retrieval/grounding regression or bad corpus.
      - alert: RedCaseRefusalRateHigh
        expr: sum(rate(redcase_answer_refusals_total[15m])) > 0.1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Answer refusal rate > 0.1/s sustained (15m window)."

      # Provider fallback storm = the primary answer provider is degrading.
      - alert: RedCaseProviderFallbackStorm
        expr: sum(rate(redcase_provider_fallbacks_total[10m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Answer LLM falling back > 2/s (10m window) — primary provider likely degraded or quota-exhausted."

      # Readiness: the DB must answer SELECT 1.
      - alert: RedCaseDatabaseDown
        expr: redcase_health_db == 0
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "/v1/health/detail reports db=down for 2m."

      # Answer-provider chain has no provisioned credential.
      - alert: RedCaseAnswerProvidersUnconfigured
        expr: redcase_health_providers == 0
        for: 5m
        labels:
          severity: page
        annotations:
          summary: "No answer-LLM credential provisioned — all /v1/query answers would 503."
```

> `redcase_health_db` / `redcase_health_providers` are gauges set (0/1) by
> each `/v1/health/detail` probe call. If you scrape `/v1/health/detail`
> with Blackbox HTTP probing instead of the gauge (e.g. in front of Cloud Run
> scale-to-zero), express readiness with `probe_success`/`probe_http_status_code`
> rules and drop the gauge dependency.

## How to runbook / page a threshold breach

1. **Fabrication gate**: treat as a security incident. Pull the matching
   `query_refused reason=citation_integrity` structlog events (they carry the
   foreign doc id, never the fabricated text) and the query_audit rows with
   `integrity_refusal` to trace the offending model run.
2. **Refusal storm**: check `/v1/health/detail` (providers field) and the
   `provider_fallback` structlog events; if a fallback was serving, the weaker
   model may be over-refusing — review the chain order, then restart it.
3. **Provider fallback storm**: check provider status / quota; a 402 (quota
   exhausted) surfaces as `reason="quota_exhausted"` on `provider_fallback`.
4. **DB down**: Cloud Run scale-to-zero may mean `SELECT 1` on a cold pool
   raced the scrape — confirm against a second probe before paging beyond the 2m `for`.

## Where the counters live

- Registry: `apps/api/app/observability.py`
- Instrumentation: `apps/api/app/retrieval/service.py` (refusals, timeouts,
  fabrications) and `apps/api/app/retrieval/clients.py` (`FallbackLLM`).
- Probe endpoints: `apps/api/app/main.py` (`/v1/health/detail`,
  `/v1/metrics`).
