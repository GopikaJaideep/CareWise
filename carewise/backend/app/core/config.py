"""Application configuration loaded from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "CareWise"
    app_version: str = "0.1.0"
    debug: bool = False

    # LLM
    anthropic_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5-20250929"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.7

    # Database
    database_url: str = "sqlite+aiosqlite:///./carewise.db"

    # Auth
    secret_key: str = "dev-only-change-in-production"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days
    algorithm: str = "HS256"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Safety
    crisis_keywords: list[str] = [
        "suicide", "kill myself", "end my life", "want to die",
        "hurt myself", "self-harm", "no reason to live",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
