"""
Centralized app configuration.

Everything is loaded from environment variables (see .env.example).
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


_base = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    # ============================================================
    # Database
    # ============================================================

    database_url: str = "sqlite:///./ai_employee_os.db"

    # ============================================================
    # AI Providers
    # ============================================================

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    ai_provider: str = "gemini"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    whisper_model: str = "whisper-1"

    # ============================================================
    # Redis / Elasticsearch
    # ============================================================

    redis_url: str = "redis://localhost:6379/0"
    elasticsearch_url: str = "http://localhost:9200"

    # ============================================================
    # Company
    # ============================================================

    company_name: str = "Your Company Pvt Ltd"
    company_address: str = "123 Business Street"
    company_email: str = "billing@yourcompany.com"
    company_phone: str = ""
    company_tax_id: str = ""
    default_tax_rate: float = 0.0
    default_currency: str = "USD"

    # ============================================================
    # Stripe
    # ============================================================

    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""

    stripe_basic_price_id: str = "price_basic_monthly"
    stripe_pro_price_id: str = "price_pro_monthly"
    stripe_business_price_id: str = "price_business_monthly"

    # ============================================================
    # Frontend
    # ============================================================

    frontend_origin: str = "http://localhost:3000"

    # ============================================================
    # Google OAuth2 (SSO)
    # Set these in backend/.env to enable real Google sign-in
    # Get credentials from: https://console.cloud.google.com/
    # ============================================================

    google_client_id: str = ""
    google_client_secret: str = ""

    # ============================================================
    # Microsoft OAuth2 (Azure AD / 365 SSO)
    # Set these in backend/.env to enable real Microsoft sign-in
    # Get credentials from: https://portal.azure.com/
    # ============================================================

    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""

    # ============================================================
    # JWT Authentication
    # ============================================================

    jwt_secret_key: str = "dev-secret-change-me-in-production"
    jwt_algorithm: str = "HS256"

    # 7 days = 10080 minutes
    jwt_expire_minutes: int = 60 * 24 * 7

    # ============================================================
    # SMTP / Email
    # ============================================================

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""
    smtp_from_name: str = ""

    # ============================================================
    # Voice & Meetings
    # ============================================================

    voice_audio_backend: str = "local"
    voice_audio_local_dir: str = "./var/voice-audio"
    voice_audio_retention_days: int = 90

    s3_bucket: str = ""
    s3_endpoint_url: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""

    diarization_url: str = ""
    diarization_api_key: str = ""

    voice_followup_check_interval_minutes: float = 30
    voice_audio_sweep_interval_minutes: float = 60 * 12

    # ============================================================
    # Background Jobs
    # ============================================================

    followup_check_interval_minutes: float = 60
    recurring_invoice_check_interval_minutes: float = 1440

    # ============================================================
    # OCR
    # ============================================================

    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_max_pages: int = 60

    # ============================================================
    # Environment Configuration
    # ============================================================

    model_config = SettingsConfigDict(
        env_file=[
            os.path.join(_base, "..", ".env"),
            os.path.join(_base, "..", "..", ".env"),
            ".env",
            "backend/.env",
        ],
        extra="ignore",
    )

    # ============================================================
    # Backward-compatible uppercase JWT properties
    #
    # Your existing auth.py currently uses:
    # settings.JWT_EXPIRE_MINUTES
    #
    # These properties allow that code to continue working.
    # ============================================================

    @property
    def JWT_SECRET_KEY(self) -> str:
        return self.jwt_secret_key

    @property
    def JWT_ALGORITHM(self) -> str:
        return self.jwt_algorithm

    @property
    def JWT_EXPIRE_MINUTES(self) -> int:
        return self.jwt_expire_minutes


settings = Settings()