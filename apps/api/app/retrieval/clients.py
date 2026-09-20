"""ZDR-compliant model clients for retrieval (Task 1.4).

CONFLICT RECORD (HANDOFF.md rule 3): Phase1-Design §3.3 references a
``zdr_client`` helper (``.embed()`` / ``.anthropic()``). Tasks 1.2/1.3 already
standardised this codebase on asyncpg + explicit constructors, so the same
contracts are provided here as protocols + factory functions instead of a
global singleton. Behavioural contract (ZDR proxy first, OpenRouter fallback,
no body logging) is unchanged.

ZDR (HANDOFF.md 2.1): these clients never log prompt bodies, document text,
or embedding inputs — token counts and ids only.
"""

import asyncio
import random
from typing import Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.config import Settings
from app.middleware.zdr import get_logger

log = get_logger("redcase.retrieval.clients")


class Embedder(Protocol):
    """texts -> one vector per text (EMBEDDING_DIMS — 1024 platform-wide,
    Jina v3 per owner ruling 2026-09-18 / migration 0007)."""

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class AnswerLLM(Protocol):
    """Grounded-answer generation. Implementations must not log bodies."""

    async def answer(self, system: str, user: str) -> str: ...


class RateLimitedError(RuntimeError):
    """Provider returned HTTP 429. Carries Retry-After seconds when the
    gateway advertised one, so callers (battery runner, fallback chain) can
    back off without re-parsing provider-specific response objects."""

    def __init__(self, retry_after: float | None, provider: str, model: str) -> None:
        self.retry_after = retry_after
        self.provider = provider
        self.model = model
        super().__init__(f"{provider}/{model} rate-limited (retry_after={retry_after})")


def _is_rate_limited(exc: Exception) -> bool:
    """True when the provider error is an HTTP 429 (openai/anthropic both
    expose status_code on their APIStatusError subclasses)."""
    return getattr(exc, "status_code", None) == 429


def _extract_retry_after(exc: Exception) -> float | None:
    """Best-effort Retry-After in seconds from provider response headers."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None) or {}
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class OpenAIEmbedder:
    """text-embedding-3-large via the no-retention ZDR proxy; OpenRouter is
    the OpenAI-compatible fallback (same wiring as scripts/ingest.py)."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        r = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in r.data]


class AnthropicLLM:
    """claude-3-5-sonnet-20241022 via the ZDR workspace key (Phase1 §3.3)."""

    MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client
        self.provider = "anthropic"
        self.model = self.MODEL

    async def answer(self, system: str, user: str) -> str:
        try:
            msg = await self._client.messages.create(
                model=self.MODEL,
                max_tokens=2048,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # re-raise non-429 unchanged; 429 -> RateLimitedError
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    _extract_retry_after(exc), self.provider, self.model
                ) from exc
            raise
        log.info(
            "llm_answer",
            model=self.MODEL,
            output_tokens=msg.usage.output_tokens,
            stop_reason=msg.stop_reason,
        )
        return msg.content[0].text


class OpenAICompatLLM:
    """OpenAI-compatible chat endpoint — the fallback answer LLM when no
    Anthropic key is provisioned. Used for DeepSeek (owner-offered) and,
    per owner ruling 2026-09-18, OpenRouter gpt-4o (the platform primary).
    Same behavioural contract as AnthropicLLM: no body logging, deterministic
    temperature, and a construction-time completion cap (bounds spend per
    answer and satisfies OpenRouter's affordability pre-check)."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        provider: str,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self.provider = provider
        self.model = model
        self._max_tokens = max_tokens

    async def answer(self, system: str, user: str) -> str:
        try:
            r = await self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:  # re-raise non-429 unchanged; 429 -> RateLimitedError
            if _is_rate_limited(exc):
                raise RateLimitedError(
                    _extract_retry_after(exc), self.provider, self.model
                ) from exc
            raise
        log.info(
            "llm_answer",
            model=self._model,
            output_tokens=r.usage.completion_tokens if r.usage else None,
            stop_reason=r.choices[0].finish_reason,
        )
        return r.choices[0].message.content


def make_embedder(settings: Settings) -> Embedder:
    """Resolve the embedding backend from config. Raises RuntimeError (to be
    mapped to 503 by the caller) when no credential is provisioned.

    Precedence: ZDR OpenAI proxy first (the design's primary path), then
    Jina (premium, provisioned — owner ruling 2026-09-18), then OpenRouter
    (fallback credential path; its free tier is rate-capped per-minute AND
    per-day, so it must not be the platform default), NVIDIA NIM last: the
    owner's NVAPI key was verified to 404 on integrate.api.nvidia.com for
    the :free model id (that id is an OpenRouter identifier), so the NIM
    branch is kept only for genuine NIM keys + NIM model ids."""
    if settings.openai_api_key:
        oai = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.zdr_embed_proxy or None,
        )
        return OpenAIEmbedder(oai, settings.embed_model)
    if settings.jina_api_key:
        jina = AsyncOpenAI(
            api_key=settings.jina_api_key.get_secret_value(),
            base_url=settings.jina_base_url,
        )
        return OpenAIEmbedder(jina, settings.jina_embed_model)
    if settings.openrouter_api_key:
        oai = AsyncOpenAI(
            api_key=settings.openrouter_api_key.get_secret_value(),
            base_url="https://openrouter.ai/api/v1",
        )
        return OpenAIEmbedder(oai, settings.embed_model)
    if settings.nvidia_api_key:
        oai = AsyncOpenAI(
            api_key=settings.nvidia_api_key.get_secret_value(),
            base_url=settings.nvidia_base_url,
        )
        return OpenAIEmbedder(oai, settings.nvidia_embed_model)
    raise RuntimeError(
        "No embedding credentials provisioned (OPENAI_API_KEY, JINA_API_KEY,"
        " OPENROUTER_API_KEY or NVAPI_KEY) — cannot embed queries."
    )


def _provider_client(name: str, settings: Settings) -> AnswerLLM | None:
    """Build the answer LLM for one provider name, or None when that
    provider's credential is not provisioned. All providers below are
    OpenAI-compatible except anthropic, so this stays config-only."""
    key: SecretStr | None = {
        "explabs": settings.explabs_api_key,
        "mistral": settings.mistral_api_key,
        "cerebras": settings.cerebras_api_key,
        "groq": settings.groq_api_key,
        "deepseek": settings.deepseek_api_key,
        "openrouter": settings.openrouter_api_key,
        "anthropic": settings.anthropic_api_key,
    }.get(name)
    if key is None:
        return None
    if name == "anthropic":
        return AnthropicLLM(AsyncAnthropic(api_key=key.get_secret_value()))
    base_url, model = {
        "explabs": (settings.explabs_base_url, settings.explabs_model),
        "mistral": (settings.mistral_base_url, settings.mistral_model),
        "cerebras": (settings.cerebras_base_url, settings.cerebras_model),
        "groq": (settings.groq_base_url, settings.groq_model),
        "deepseek": (settings.deepseek_base_url, settings.deepseek_model),
        "openrouter": ("https://openrouter.ai/api/v1", settings.llm_model),
    }[name]
    client = AsyncOpenAI(
        api_key=key.get_secret_value(),
        base_url=base_url,
        timeout=180.0,
        max_retries=4,
    )
    return OpenAICompatLLM(
        client, model, provider=name, max_tokens=settings.answer_max_tokens
    )


# Fallback-chain backoff (per-call): honor a gateway Retry-After only when it
# is small enough to keep the whole retry+fallback sequence inside
# answer_timeout_s (20s). Per-minute limits are the battery runner's job
# (15/30/60s), not the per-call chain's.
_FALLBACK_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
MAX_FALLBACK_RETRIES = 3


def _fallback_delay(retry_after: float | None, retry: int) -> float:
    """Jittered per-call backoff (retry is 0-indexed): 1/2/4s base +0-50%
    jitter, or an advertised Retry-After when it is <= 3s."""
    if retry_after is not None and 0 < retry_after <= 3.0:
        return retry_after
    base = _FALLBACK_BACKOFF_SECONDS[retry]
    return base + random.uniform(0.0, base * 0.5)  # noqa: S311 — jitter, not crypto


def _failure_reason(exc: Exception) -> str:
    """Classify a hard failure for the audit-trail structlog event."""
    if getattr(exc, "status_code", None) == 402:
        return "quota_exhausted"
    return "hard_failure"


class FallbackLLM:
    """Answer LLM with a two-tier provider error policy.

    Tier 1 — 429/transient: retry the SAME provider with backoff (max 3)
    before any fallback. Falling back on a momentary limit would silently
    downgrade to a weaker model mid-run and poison provider-comparison
    evidence.

    Tier 2 — hard failure / exhausted quota (e.g. 402): fall through to the
    next provider in the chain immediately.

    Content refusals are never errors: the model returns the no-precedence
    sentence like any other answer, so neither tier triggers. ``provider`` /
    ``model`` reflect the provider that ACTUALLY served the last call (the
    caller records these in query_audit).
    """

    def __init__(self, providers: list[tuple[str, AnswerLLM]]) -> None:
        self._providers = providers
        self.provider: str | None = None
        self.model: str | None = None

    async def answer(self, system: str, user: str) -> str:
        tried: list[str] = []
        last_exc: Exception | None = None
        for name, llm in self._providers:
            for rl in range(MAX_FALLBACK_RETRIES + 1):
                try:
                    out = await llm.answer(system, user)
                    self.provider = getattr(llm, "provider", name)
                    self.model = getattr(llm, "model", None)
                    return out
                except RateLimitedError as exc:
                    if rl == MAX_FALLBACK_RETRIES:
                        tried.append(name)
                        last_exc = exc
                        log.warn(
                            "provider_fallback",
                            provider=name,
                            reason="rate_limited",
                            retries=MAX_FALLBACK_RETRIES,
                            tried=list(tried),
                        )
                        break
                    delay = _fallback_delay(exc.retry_after, rl)
                    log.info(
                        "provider_rate_limited_retry",
                        provider=name,
                        retry=rl + 1,
                        delay_s=round(delay, 1),
                    )
                    await asyncio.sleep(delay)
                except Exception as exc:  # hard failure -> fall through
                    tried.append(name)
                    last_exc = exc
                    log.warn(
                        "provider_fallback",
                        provider=name,
                        reason=_failure_reason(exc),
                        tried=list(tried),
                    )
                    break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("answer provider chain exhausted with no providers")


def make_llm(settings: Settings) -> AnswerLLM:
    """Resolve the answer LLM as a runtime-fallback chain.

    Order: ANSWER_MODEL_PRIMARY, then each ANSWER_MODEL_FALLBACK entry, then
    anthropic (the design-doc ZDR primary, used automatically when keyed) as
    final implicit fallback, then openrouter. Provider names only — models and
    endpoints live in Settings. Every provisioned name becomes one link in a
    FallbackLLM chain with the two-tier error policy above. Raises when
    nothing is provisioned.

    Provider roles (owner ruling 2026-09-18): groq = platform primary;
    deepseek = EXPERIMENTAL FALLBACK; anthropic = design primary. The chain
    records the ACTUAL serving provider per call (FallbackLLM.provider), which
    answer_question persists to query_audit — a run configured for one primary
    is never silently mis-attributed when a fallback serves."""
    names: list[str] = []
    for name in [settings.answer_model_primary, *settings.answer_model_fallback.split(",")]:
        name = name.strip()
        if name and name not in names:
            names.append(name)
    for implicit in ("anthropic", "openrouter"):
        if implicit not in names:
            names.append(implicit)

    providers: list[tuple[str, AnswerLLM]] = []
    for name in names:
        llm = _provider_client(name, settings)
        if llm is not None:
            providers.append((name, llm))
    if not providers:
        raise RuntimeError(
            "No answer-LLM credential provisioned (EXPLABS_API_KEY, GROQ_API_KEY,"
            " DEEPSEEK_API_KEY, OPENROUTER_API_KEY or ANTHROPIC_API_KEY)"
            " — cannot generate answers."
        )
    return FallbackLLM(providers)