from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openrouter_api_key: SecretStr | None = None
    jwt_secret: SecretStr = SecretStr("local-development-only")
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
