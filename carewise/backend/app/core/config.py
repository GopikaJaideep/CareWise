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
    # Plain comma-separated string, not list[str]: pydantic-settings tries to
    # JSON-parse env values for list-typed fields, and a malformed array
    # pasted into a dashboard's env-var field (missing/mismatched quotes or
    # brackets) crashes the app on startup. A plain string is far more
    # forgiving to hand-edit.
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Password reset email (Resend)
    resend_api_key: str = ""
    resend_from_email: str = "CareWise <onboarding@resend.dev>"
    frontend_url: str = "http://localhost:5173"
    reset_token_expire_minutes: int = 30

    # Push notifications (Web Push / VAPID)
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claim_email: str = "mailto:admin@example.com"
    morning_reminder_hour_utc: int = 8

    # Safety
    crisis_keywords: str = (
        "suicide,kill myself,end my life,want to die,"
        "hurt myself,self-harm,no reason to live"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def crisis_keywords_list(self) -> list[str]:
        return [kw.strip() for kw in self.crisis_keywords.split(",") if kw.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
