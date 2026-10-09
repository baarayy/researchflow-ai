"""Application settings, loaded from environment variables (and an optional .env file).

Every secret and tunable lives here so the rest of the code never reads os.environ directly.
Validation runs at startup: a misconfigured deployment fails fast instead of mid-research.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- Database -----------------------------------------------------------------------
    # SQLAlchemy URL (psycopg 3 driver). The LangGraph checkpointer derives a plain libpq URL.
    database_url: str = "postgresql+psycopg://researchflow:researchflow@localhost:5433/researchflow"

    # --- Model providers ----------------------------------------------------------------
    llm_provider: Literal["openai", "mock"] = "mock"
    llm_model: str = "gpt-5-mini"
    llm_temperature: float | None = None  # some reasoning models reject temperature
    llm_timeout_seconds: float = 90
    openai_api_key: SecretStr | None = None

    embedding_provider: Literal["openai", "mock"] = "mock"
    embedding_model: str = "text-embedding-3-small"
    # Baked into the pgvector column at migration time; changing it needs a re-index.
    embedding_dim: int = Field(1536, ge=8, le=2000)

    search_provider: Literal["tavily", "mock"] = "mock"
    tavily_api_key: SecretStr | None = None
    search_max_results: int = Field(5, ge=1, le=10)
    search_timeout_seconds: float = 20
    external_max_retries: int = Field(2, ge=0, le=5)

    # --- Research workflow limits -----------------------------------------------------
    max_research_iterations: int = Field(3, ge=1, le=10)
    max_tasks_per_session: int = Field(12, ge=1, le=50)
    max_tool_calls_per_session: int = Field(30, ge=1, le=200)
    coverage_threshold: float = Field(0.75, ge=0, le=1)
    outdated_after_days: int = 730

    # --- RAG ----------------------------------------------------------------------------
    chunk_size: int = Field(1000, ge=100, le=8000)
    chunk_overlap: int = Field(150, ge=0, le=2000)
    retrieval_top_k: int = Field(5, ge=1, le=50)
    retrieval_min_score: float = Field(0.0, ge=-1, le=1)

    # --- Uploads ------------------------------------------------------------------------
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = Field(20, ge=1, le=200)

    # --- API protection -----------------------------------------------------------------
    rate_limit_per_minute: int = Field(30, ge=1)
    # Development-only auth: trusts the X-User-Id header. Never enable in production.
    dev_auth_enabled: bool = True

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        needs_openai = self.llm_provider == "openai" or self.embedding_provider == "openai"
        if needs_openai and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when an OpenAI provider is selected")
        if self.search_provider == "tavily" and not self.tavily_api_key:
            raise ValueError("TAVILY_API_KEY is required when SEARCH_PROVIDER=tavily")
        if self.app_env == "production" and self.dev_auth_enabled:
            raise ValueError("DEV_AUTH_ENABLED must be false in production; add real auth")
        return self

    @property
    def checkpoint_database_url(self) -> str:
        """libpq-style URL for langgraph-checkpoint-postgres (it uses psycopg directly)."""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def demo_mode(self) -> bool:
        return "mock" in (self.llm_provider, self.search_provider, self.embedding_provider)


@lru_cache
def get_settings() -> Settings:
    return Settings()
