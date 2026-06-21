from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    ai_model: str = "claude-haiku-4-5"
    ai_timeout_seconds: float = 12.0

    owner_email: str = "owner@example.com"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "noreply@devlanding.local"

    rate_limit_max: int = 5
    rate_limit_window_seconds: int = 600

    cors_origins: str = "*"
    data_dir: str = "data"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def ai_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
