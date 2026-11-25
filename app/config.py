import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Configuracao lida do ambiente, com defaults seguros para rodar local."""

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./docextract.db")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-troque-em-producao")
    token_minutes: int = int(os.getenv("TOKEN_MINUTES", "120"))
    queue_mode: str = os.getenv("QUEUE_MODE", "inline")  # inline | thread | redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    queue_name: str = os.getenv("QUEUE_NAME", "docextract:fila")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


settings = Settings()
