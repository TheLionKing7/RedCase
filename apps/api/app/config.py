"""RedCase configuration — pydantic-settings.

HANDOFF.md 2/3: NO secrets in code. Every secret is read from the
environment (backed by AWS Secrets Manager in deployment) and wrapped in
SecretStr so it can never be rendered into logs or reprs accidentally.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Brand tokens (HANDOFF.md 2.6) — non-secret, safe to ship in config.
BRAND_CRIMSON = "#D0021B"
BRAND_OBSIDIAN = "#0F1115"
BRAND_VELLUM = "#E2C044"


class Settings(BaseSettings):
    """Environment-driven settings. Secrets default to None: the app factory
    and health checks must boot without them (tests, CI lint), and any code
    path that actually needs a secret must call require_secrets() first."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Runtime
    app_name: str = "RedCase API"
    env: str = "dev"  # dev | staging | prod
    log_level: str = "INFO"

    # Secrets — HANDOFF.md 3 registry. Never hardcode; never log.
    supabase_url: str | None = None
    supabase_service_role: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None  # ZDR workspace key
    openai_api_key: SecretStr | None = None  # embeddings via ZDR proxy
    openrouter_api_key: SecretStr | None = None  # OpenAI-compatible embeddings fallback
    nvidia_api_key: SecretStr | None = None  # NVIDIA NIM (build.nvidia.com) embeddings
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # Default is a genuine NIM model id: the nemotron :free id is an
    # OpenRouter identifier and 404s on NIM (verified 2026-09-17).
    nvidia_embed_model: str = "nvidia/nv-embedqa-e5-v5"
    jina_api_key: SecretStr | None = None  # premium embeddings (owner 2026-09-18)
    jina_embed_model: str = "jina-embeddings-v3"  # 1024 dims
    jina_base_url: str = "https://api.jina.ai/v1"  # OpenAI-compatible
    deepseek_api_key: SecretStr | None = None  # OpenAI-compatible chat fallback
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    groq_api_key: SecretStr | None = None  # OpenAI-compatible chat (owner 2026-09-18)
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # gpt-oss-120b: the strongest chat model served on the owner's Groq
    # account (llama-3.3-70b-versatile 404s there — removed from the catalog;
    # verified 2026-09-18). Reasoning model: accepts temperature=0 (verified),
    # reasoning tokens are billed but do not enter `content`, and no
    # max_tokens cap is sent, so the citation block cannot be truncated.
    groq_model: str = "openai/gpt-oss-120b"
    cerebras_api_key: SecretStr | None = None  # OpenAI-compatible chat (owner 2026-09-18)
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    # Cerebras' catalog id drops the openai/ prefix (verified against
    # GET /v1/models 2026-09-18). Same model class as the Groq entry.
    cerebras_model: str = "gpt-oss-120b"
    mistral_api_key: SecretStr | None = None  # OpenAI-compatible chat (owner 2026-09-18)
    mistral_base_url: str = "https://api.mistral.ai/v1"
    # Free-tier reality (verified 2026-09-18): the account's rate limit for
    # mistral-small/medium is 0 req/min — only the Ministrals are enabled.
    # ministral-8b is therefore the only served model; a 5-ID battery pilot
    # gauges its citation discipline before any full run.
    mistral_model: str = "ministral-8b-latest"
    # Experiential Labs paid gateway (owner 2026-09-20): OpenAI-compatible
    # chat over a 288-model catalog (GET /v1/models verified). Hosts the
    # Claude Sonnet class — the Phase1-Design §3.3 ZDR-primary family — so
    # explabs is the premium answer-model candidate for the battery's
    # answer-LLM-limited failures (DeepSeek over-refusal/flap class).
    explabs_api_key: SecretStr | None = None
    explabs_base_url: str = "https://api.experientiallabs.ai/v1"
    explabs_model: str = "claude-sonnet-4.5"
    zdr_embed_proxy: str | None = None  # no-retention embedding gateway URL
    database_url: str | None = None  # asyncpg DSN; Secrets Manager in prod
    supabase_jwt_secret: SecretStr | None = None  # verifies Supabase JWTs (ruling 3)
    internal_sweep_token: SecretStr | None = None  # authenticates POST /v1/internal/sweep
    # Vault A envelope crypto (Phase 2 Task 2.2): key provider selection.
    # local = dev fallback (VAULT_A_MASTER_KEY, 64-char hex, never commit);
    # kms = production backend, fails closed until the KMS wiring lands.
    vault_a_key_provider: str = "local"
    vault_a_master_key: SecretStr | None = None
    storage_public_url: str | None = None  # public URL prefix for source_pdf_path

    # Web
    cors_origins: str = "http://localhost:7100,http://127.0.0.1:7100"

    # Retrieval tuning — HANDOFF.md 3 env config
    # Platform embedding model (owner ruling 2026-09-18, superseding the
    # 2026-09-17 nemotron/OpenRouter ruling): Jina v3 via the premium
    # JINA_API_KEY — 1024 dims (migration 0007). The OpenRouter free tier
    # (20 embeds/min + 50 free-model requests/day, daily cap exhausted
    # mid-calibration 2026-09-18) is demoted to fallback credential path;
    # DeepSeek serves chat models only and has no embeddings API. If the
    # ZDR OpenAI proxy path is provisioned instead, embed_model MUST be
    # set to a 1024-dim model — ingest validates EMBEDDING_DIMS per batch.
    embed_model: str = "jina-embeddings-v3"
    # Calibrated 2026-09-18 via scripts/calibrate_gate against the 50-question
    # citation battery with the platform embedder (jina-embeddings-v3, 1024d),
    # measuring the EXACT runtime metric via RetrievalService.candidates()
    # (vsim of the top-hybrid-score chunk — see the script docstring):
    # answer-class 0.526-0.761, refusal-class 0.415-0.694. Gate 0.52 sits
    # just below the lowest answer-class score so every answerable question
    # enters the grounding pipeline; the corpus-adjacent refusal questions
    # above the gate are caught by the rule-3 insufficient-grounding
    # refusal (service.py), not by similarity alone — pure vsim separation
    # tops out at 43/50. Phase1-Design's 0.78 was calibrated for
    # text-embedding-3-large and refuses every question under Jina (verified).
    vector_gate: float = 0.52
    # Presentation budget (retrieval.service.retrieve): how many passages are
    # shown to the answer LLM, and how many of one document at most. The
    # gating matrix (owner 2026-09-18) varies these without code edits.
    retrieval_top_k: int = 8
    retrieval_per_doc_cap: int = 3
    # When true, is_ratio chunks bypass the per-document cap: a document's
    # holding passage is never crowded out by its own caption/header chunks
    # (the B11 failure mode). The 2x2 gating matrix runs with this on.
    retrieval_ratio_exempt: bool = False
    # Answer-model provider selection (owner ruling 2026-09-18, Task 1.7
    # step 3/1): env-selectable primary + fallback chain, names only.
    # Resolution order: ANSWER_MODEL_PRIMARY, then ANSWER_MODEL_FALLBACK
    # (comma-separated chain, first provisioned credential wins). OpenRouter
    # (gpt-4o) is the platform primary — Groq's free-tier 8k ITPM ceiling
    # rejects battery-size prompts and Cerebras 402s with no account quota
    # (both verified 2026-09-18). DeepSeek is explicitly EXPERIMENTAL
    # FALLBACK (latency + flapping evidence below). Anthropic
    # (claude-3-5-sonnet-20241022) remains the design-doc ZDR primary and is
    # used automatically when an Anthropic key is provisioned.
    answer_model_primary: str = "openrouter"
    answer_model_fallback: str = "cerebras,groq,deepseek"
    # Chat model served through OpenRouter (the platform answer model,
    # owner 2026-09-18: gpt-4o — verified temperature=0 accepted, ~10k-token
    # grounded prompts served in ~3s). gpt-4o is not a ZDR-class endpoint:
    # OpenAI API default retention applies (no training; 30-day abuse-
    # monitoring retention unless a ZDR agreement is in place) — same
    # verification-item class as Groq/Cerebras console zero-retention.
    llm_model: str = "openai/gpt-4o"
    # Answer-call ceiling (Task 1.7 step 2, owner-approved 2026-09-18): a
    # single answer LLM call exceeding this is logged as a refusal for that
    # attempt and the one-retry-on-refusal policy applies. Removes the
    # 205s-tail outliers recorded in query_audit (measuring first, then
    # capping, would report a defect already scheduled for removal).
    answer_timeout_s: float = 20.0
    # Per-call completion cap. Bounds spend per answer (OpenRouter's
    # affordability pre-check sizes against max_tokens), and grounded legal
    # answers fit comfortably — the largest observed battery answer is
    # <2k tokens; the old 16k+ row was a passage-echo artifact, now stripped.
    answer_max_tokens: int = 4096

    # --- Part 2: public signup hardening (HANDOFF §4 growth surface) ---
    # The system's first UNAUTHENTICATED write path is rate-limited per IP and
    # per normalized email (process-local sliding window — no Redis dependency in
    # this phase; the in-memory store is a single-proc approximation and is
    # documented as a production caveat behind Cloudflare, which also rate-limits).
    signup_rate_limit_per_ip: int = 10         # applications per window per IP
    signup_rate_limit_per_email: int = 3        # applications per window per email
    signup_rate_window_s: int = 900             # 15-minute sliding window
    verify_rate_limit_per_ip: int = 20           # verify attempts per window per IP
    # Email-verification token lifetime (Part 2 DoD gate).
    signup_verify_ttl_s: int = 86400           # 24h

    # --- Part 3 Slice 1: invitee bootstrap (POST /v1/invites/accept) ---
    # Another UNAUTHENTICATED write path, throttled per IP and per invite token
    # (same process-local window + Cloudflare-edge caveat as signup). The invite
    # link itself is short-lived (7 days) so a leaked/forwarded link cannot be
    # redeemed indefinitely.
    invite_accept_rate_limit_per_ip: int = 10        # accept attempts per window per IP
    invite_accept_rate_limit_per_token: int = 5      # accept attempts per window per token
    invite_accept_rate_window_s: int = 900           # 15-minute sliding window
    invite_token_ttl_s: int = 604800                # 7 days

    def require_secrets(self, *names: str) -> None:
        """Fail fast when a code path needs a secret that is not provisioned."""
        missing = [n for n in names if getattr(self, n, None) is None]
        if missing:
            raise RuntimeError(
                f"Missing required secrets/config: {', '.join(missing)}. "
                "Provision them via AWS Secrets Manager (see HANDOFF.md 3)."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
