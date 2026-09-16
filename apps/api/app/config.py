"""RedCase configuration — pydantic-settings.

HANDOFF.md §2/§3: NO secrets in code. Every secret is read from the
environment (backed by AWS Secrets Manager in deployment) and wrapped in
SecretStr so it can never be rendered into logs or reprs accidentally.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Brand tokens (HANDOFF.md §2.6) — non-secret, safe to ship in config.
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

    # Secrets — HANDOFF.md §3 registry. Never hardcode; never log.
    supabase_url: str | None = None
    supabase_service_role: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None  # ZDR workspace key
    openai_api_key: SecretStr | None = None  # embeddings via ZDR proxy
    zdr_embed_proxy: str | None = None  # no-retention embedding gateway URL

    # Retrieval tuning — HANDOFF.md §3 env config
    embed_model: str = "text-embedding-3-large"
    vector_gate: float = 0.78  # SIMILARITY_THRESHOLD, calibrated in Phase 1 §5

    def require_secrets(self, *names: str) -> None:
        """Fail fast when a code path needs a secret that is not provisioned."""
        missing = [n for n in names if getattr(self, n, None) is None]
        if missing:
            raise RuntimeError(
                f"Missing required secrets/config: {', '.join(missing)}. "
                "Provision them via AWS Secrets Manager (see HANDOFF.md §3)."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
