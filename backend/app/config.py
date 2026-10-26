"""
═══════════════════════════════════════════════════════════════════
  Project Phoenix — Backend Configuration
  All tunables in one place. Override via environment variables.
═══════════════════════════════════════════════════════════════════
"""

import os


class Settings:
    """Central config — reads from env vars with sane defaults."""

    # ── Server ──
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "3000"))

    # ── CORS ──
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,null"
    ).split(",")

    # ── OTP ──
    OTP_TTL_SECONDS: int = int(os.getenv("OTP_TTL_SECONDS", "300"))  # 5 minutes
    OTP_LENGTH: int = 6
    OTP_TEST_CODE: str = "123456"  # Always accepted in dev/demo mode

    # ── Redis ──
    REDIS_URL: str = os.getenv("REDIS_URL", "")  # Empty = use in-memory fallback
    DRAFT_TTL_SECONDS: int = int(os.getenv("DRAFT_TTL_SECONDS", "86400"))  # 24 hours

    # ── AWS S3 (for pre-signed upload URLs) ──
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "phoenix-uploads")
    S3_UPLOAD_EXPIRY: int = int(os.getenv("S3_UPLOAD_EXPIRY", "300"))  # 5 min

    # ── Rate Limiting ──
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # ── Idempotency ──
    IDEMPOTENCY_TTL_SECONDS: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 hour

    # ── Environment ──
    ENV: str = os.getenv("ENV", "development")  # development | staging | production

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


settings = Settings()
