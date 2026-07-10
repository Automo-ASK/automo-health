from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Application
    app_name: str = "Automo Health"
    environment: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = (
        "postgresql+psycopg2://automo:automo@localhost:5432/automo_health"
    )

    # Celery / Redis
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Booking / slots
    slot_hold_ttl_seconds: int = 600
    booking_payment_ttl_seconds: int = 900

    # Paystack
    paystack_secret_key: str = "sk_test_changeme"
    paystack_public_key: str = "pk_test_changeme"
    paystack_base_url: str = "https://api.paystack.co"
    default_currency: str = "NGN"
    paystack_callback_url: str = "http://localhost:8000/api/v1/payments/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
