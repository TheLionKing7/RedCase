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
    zdr_embed_proxy: str | None = None  # no-retention embedding gateway URL
    database_url: str | None = None  # asyncpg DSN; Secrets Manager in prod
    supabase_jwt_secret: SecretStr | None = None  # verifies Supabase JWTs (ruling 3)
    storage_public_url: str | None = None  # public URL prefix for source_pdf_path

    # Web
    cors_origins: str = "http://localhost:7100,http://127.0.0.1:7100"

    # Retrieval tuning — HANDOFF.md 3 env config
    # Platform embedding model (owner 2026-09-17): nvidia nemotron via
    # OpenRouter (2048 dims — the only provisioned credential path; the
    # :free model id is an OpenRouter identifier, NOT a NIM model). If the
    # ZDR OpenAI proxy path is provisioned instead, embed_model MUST be set
    # to a 2048-dim model — ingest validates EMBEDDING_DIMS per batch.
    embed_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    vector_gate: float = 0.78  # SIMILARITY_THRESHOLD, calibrated in Phase 1 5

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
