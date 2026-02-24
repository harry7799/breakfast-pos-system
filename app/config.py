from __future__ import annotations

import os
import secrets

from dotenv import load_dotenv

load_dotenv()

_INSECURE_KEY_PLACEHOLDERS = {
    "change-this-secret-in-production",
    "replace-with-long-random-secret",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name: str = os.getenv("APP_NAME", "Breakfast Store System")
    app_env: str = os.getenv("APP_ENV", "development")
    auth_disabled: bool = _env_bool("AUTH_DISABLED", True)
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./breakfast.db")
    redis_url: str = os.getenv("REDIS_URL", "").strip()
    trust_proxy_headers: bool = _env_bool("TRUST_PROXY_HEADERS", False)
    cors_origins: str = os.getenv("CORS_ORIGINS", "")
    token_expire_minutes: int = int(os.getenv("TOKEN_EXPIRE_MINUTES", "720"))
    login_rate_window_seconds: int = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "60"))
    login_rate_max_attempts: int = int(os.getenv("LOGIN_RATE_MAX_ATTEMPTS", "10"))

    def __init__(self) -> None:
        raw_key = os.getenv("SECRET_KEY", "")
        if self.app_env == "production" and (not raw_key or raw_key in _INSECURE_KEY_PLACEHOLDERS):
            raise RuntimeError(
                "SECRET_KEY is missing or insecure. "
                "Set a strong random SECRET_KEY in production."
            )
        self.secret_key: str = raw_key if raw_key and raw_key not in _INSECURE_KEY_PLACEHOLDERS else secrets.token_hex(32)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
