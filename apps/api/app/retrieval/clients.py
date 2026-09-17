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

from app.config import Settings
from app.middleware.zdr import get_logger

log = get_logger("redcase.retrieval.clients")


class Embedder(Protocol):
    """texts -> one vector per text (EMBEDDING_DIMS — 2048 platform-wide)."""

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


def make_embedder(settings: Settings) -> Embedder:
    """Resolve the embedding backend from config. Raises RuntimeError (to be
    mapped to 503 by the caller) when no credential is provisioned.

    Precedence: ZDR OpenAI proxy first (the design's primary path), then
    OpenRouter (the provisioned path — owner 2026-09-17), NVIDIA NIM last:
    the owner's NVAPI key was verified to 404 on integrate.api.nvidia.com
    for the :free model id (that id is an OpenRouter identifier), so the
    NIM branch is kept only for genuine NIM keys + NIM model ids."""
    if settings.openai_api_key:
        oai = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.zdr_embed_proxy or None,
        )
        return OpenAIEmbedder(oai, settings.embed_model)
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
        "No embedding credentials provisioned (OPENAI_API_KEY,"
        " OPENROUTER_API_KEY or NVAPI_KEY) — cannot embed queries."
    )


def make_llm(settings: Settings) -> AnswerLLM:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not provisioned — cannot generate grounded answers."
        )
    return AnthropicLLM(AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()))
