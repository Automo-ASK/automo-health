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

    # Payments
    # Active provider for virtual accounts / links ("paystack" or "squad").
    payment_provider: str = "paystack"
    default_currency: str = "NGN"

    # Paystack
    paystack_secret_key: str = "sk_test_changeme"
    paystack_public_key: str = "pk_test_changeme"
    paystack_base_url: str = "https://api.paystack.co"
    paystack_callback_url: str = "http://localhost:8000/api/v1/payments/callback"
    # Bank used when provisioning a dedicated virtual account (test: wema-bank/titan-paystack).
    paystack_dva_preferred_bank: str = "test-bank"

    # Notifications
    # Optional outbound webhook that receives notification events as JSON.
    notifications_webhook_url: str | None = None
    # When true, notification hooks are enqueued to Celery (requires a broker+worker).
    # When false (default), they are delivered inline — simpler for dev/test.
    notifications_async: bool = False

    # Africa's Talking
    at_username: str = "sandbox"
    at_api_key: str = "changeme"
    at_sender_id: str = "AUTOMO"
    at_shortcode: str = "*384*1234#"

    # Gemini AI
    google_api_key: str = "changeme"
    gemini_model: str = "gemini-2.5-pro"
    ai_max_history_turns: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
