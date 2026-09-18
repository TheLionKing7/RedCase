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

    async def answer(self, system: str, user: str) -> str:
        msg = await self._client.messages.create(
            model=self.MODEL,
            max_tokens=2048,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
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

    def __init__(self, client: AsyncOpenAI, model: str, max_tokens: int = 4096) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def answer(self, system: str, user: str) -> str:
        r = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
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
    return OpenAICompatLLM(client, model, max_tokens=settings.answer_max_tokens)


def make_llm(settings: Settings) -> AnswerLLM:
    """Resolve the answer LLM from the env-selectable provider chain.

    Order: ANSWER_MODEL_PRIMARY, then each ANSWER_MODEL_FALLBACK entry, then
    anthropic (the design-doc ZDR primary, used automatically when keyed) as
    final implicit fallback. Provider names only — models and endpoints live
    in Settings. Raises when nothing is provisioned.

    Provider roles (owner ruling 2026-09-18): groq = platform primary;
    deepseek = EXPERIMENTAL FALLBACK (per-call latency 4-10s and ~50%
    first-attempt flapping measured 2026-09-18 — see
    docs/calibration/phase1-jina.md); anthropic = design primary, currently
    unprovisioned. DEVIATION from Phase1-Design §3.3 (Claude 3.5 Sonnet via
    the ZDR workspace key as default): recorded per HANDOFF.md rule 3 — the
    code honours the design the moment ANTHROPIC_API_KEY is provisioned."""
    chain = [settings.answer_model_primary, *settings.answer_model_fallback.split(",")]
    for name in chain:
        llm = _provider_client(name.strip(), settings)
        if llm is not None:
            return llm
    for implicit in ("anthropic", "openrouter"):
        llm = _provider_client(implicit, settings)
        if llm is not None:
            return llm
    raise RuntimeError(
        "No answer-LLM credential provisioned (GROQ_API_KEY, DEEPSEEK_API_KEY,"
        " OPENROUTER_API_KEY or ANTHROPIC_API_KEY) — cannot generate answers."
    )