"""Central, validated application settings.

Every other module imports `get_settings()` instead of reading
environment variables directly, so configuration lives in one place.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "pr-reviewer"
    log_level: str = "INFO"

    # Gemini
    google_api_key: SecretStr
    gemini_model: str = "gemini-2.5-flash"
    llm_temperature: float = 0.1
    llm_max_concurrency: int = 2
    llm_max_retries: int = 3

    # GitHub
    github_token: SecretStr
    github_webhook_secret: SecretStr | None = None

    # Database
    database_url: str

    # LangSmith (optional)
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "pr-reviewer"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()