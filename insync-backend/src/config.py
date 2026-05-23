from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = Field(default="")
    openai_model_parser: str = "gpt-4o-mini"
    openai_model_scorer: str = "gpt-4o"
    openai_request_timeout: int = 60
    openai_max_concurrency: int = 20

    # LlamaParse
    llama_cloud_api_key: str = Field(default="")
    llamaparse_result_type: str = "text"
    llamaparse_mode: str = "premium"

    # Supabase
    supabase_url: str = Field(default="")
    supabase_service_key: str = Field(default="")
    supabase_anon_key: str = Field(default="")

    # Redis (for content-hash caches + cost telemetry)
    redis_url: str = "redis://localhost:6379/0"
    # Rate-limit storage. Defaults to in-memory (works for single-instance deploys);
    # set to e.g. "redis://host:6379/1" for multi-instance deploys.
    rate_limit_storage: str = "memory://"

    # CRM
    crm_webhook_url: str = Field(default="")
    crm_webhook_secret: str = Field(default="")
    slack_webhook_url: str = Field(default="")

    # Email
    resend_api_key: str = Field(default="")
    email_from: str = "tools@insync.space"
    email_from_name: str = "Insync Recruitment"

    # App
    frontend_url: str = "http://localhost:8080"
    allowed_origins: str = (
        "http://localhost:5173,http://localhost:8080,http://localhost:8000"
    )
    environment: Literal["development", "staging", "production"] = "development"
    daily_cost_alert_usd: float = 50.0
    log_level: str = "INFO"
    free_tier_daily_resume_cap: int = 100

    # Cache TTLs (seconds)
    cache_ttl_result: int = 3600
    cache_ttl_file_parse: int = 86_400
    cache_ttl_jd_parse: int = 86_400

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
