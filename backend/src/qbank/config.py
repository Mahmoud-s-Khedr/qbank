from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 32
DEV_JWT_SECRET = "local-development-only-not-for-production"  # noqa: S105 -- public development default


class LLMStageConfig(BaseModel):
    model: str
    max_tokens: int = 4096
    reasoning: Literal["off", "low", "medium"] = "off"
    temperature: float = 0.0


def default_stage_models() -> dict[str, LLMStageConfig]:
    return {
        "extract": LLMStageConfig(model="google/gemini-3.8-flash"),
        "extract_strong": LLMStageConfig(model="google/gemini-3.8-flash", reasoning="low"),
        "eval": LLMStageConfig(model="google/gemini-3.8-flash"),
        "verify": LLMStageConfig(model="openai/gpt-6-luna"),
        **{
            stage: LLMStageConfig(model="anthropic/claude-haiku-5.5")
            for stage in ("structure", "classify", "compose")
        },
    }


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QBANK_", env_file=("../.env", ".env"), extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://qbank:qbank@localhost:25432/qbank"
    redis_url: str = "redis://localhost:26379/0"
    s3_endpoint_url: str = "http://localhost:29000"
    s3_bucket: str = "qbank"
    s3_access_key: str = "qbanklocal"
    s3_secret_key: SecretStr = SecretStr("qbanklocalpassword")
    storage_backend: Literal["s3", "local"] = "s3"
    storage_local_root: str = "./storage"
    max_pages: int = 1000
    max_upload_mb: int = 300
    worker_cache_dir: str | None = None
    worker_cache_max_mb: int = 2048
    render_batch_size: int = 8
    extract_image_max_side: int = 1600
    extract_fallback_threshold: float = 0.5
    review_threshold: float = 0.75
    render_dpi_display: int = 150
    render_dpi_hires: int = 300
    sse_interval: float = 1.0
    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_mode: Literal["live", "fake", "recorded"] = "live"
    llm_timeout_s: float = 120
    llm_max_retries: int = 3
    llm_stage_models: dict[str, LLMStageConfig] = Field(default_factory=default_stage_models)
    llm_allowed_models: list[str] = Field(
        default_factory=lambda: [
            "google/gemini-3.8-flash",
            "qwen/qwen3.8-flash",
            "openai/gpt-6-luna",
            "anthropic/claude-haiku-5.5",
            "nvidia/nemotron-3.5-super-vl:free",
        ]
    )
    llm_max_price_in_per_m: float = 1.0
    llm_max_price_out_per_m: float = 5.0
    llm_budget_usd: float = 0.50
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    cookie_secure: bool = False
    session_ttl_minutes: int = 720
    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if self.worker_cache_max_mb <= 0 or self.render_batch_size <= 0:
            raise ValueError("Cache size and batch size must be positive")
        if self.session_ttl_minutes <= 0:
            raise ValueError("session_ttl_minutes must be positive")
        if self.env == "prod" and (
            secret == DEV_JWT_SECRET or len(secret) < MIN_SECRET_LENGTH or not self.cookie_secure
        ):
            raise ValueError("Production requires a strong JWT secret and secure cookies")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
