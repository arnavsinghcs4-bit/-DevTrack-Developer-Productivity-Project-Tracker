from typing import List, Union
from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_DEFAULT_SECRET_KEY = "devtrack_super_secret_jwt_key_change_in_production_2026"
SUPPORTED_ENVIRONMENTS = {
    "development",
    "dev",
    "staging",
    "production",
    "prod",
    "testing",
    "test",
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "DevTrack API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Security
    SECRET_KEY: str = DEV_DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    # Short-lived by design: the access token only has to survive between
    # silent refreshes (see POST /auth/refresh), so a stolen JWT expires
    # quickly while the rotating refresh token handles long sessions.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        raw_env = self.ENVIRONMENT
        if not raw_env or not raw_env.strip():
            raise ValueError(
                "ENVIRONMENT cannot be empty. "
                "Supported values are: 'development' (dev), 'staging', 'production' (prod), 'testing' (test)."
            )
        env = raw_env.strip().lower()
        if env not in SUPPORTED_ENVIRONMENTS:
            raise ValueError(
                f"Invalid ENVIRONMENT '{raw_env}'. "
                f"Supported values are: 'development' (dev), 'staging', 'production' (prod), 'testing' (test)."
            )
        self.ENVIRONMENT = env

        # Normalize secret key whitespace so the exact stripped value is used for JWT operations
        secret = self.SECRET_KEY.strip() if self.SECRET_KEY else ""
        self.SECRET_KEY = secret

        if env in ("production", "prod", "staging"):
            if not secret:
                raise ValueError("SECRET_KEY is required and cannot be empty in production.")
            if secret == DEV_DEFAULT_SECRET_KEY:
                raise ValueError(
                    "Insecure default SECRET_KEY cannot be used in production. "
                    "Please configure a strong, unique SECRET_KEY in your environment."
                )
            if len(secret) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters long (excluding whitespace) in production."
                )
        return self

    # Rate limiting (auth endpoints) - see app/core/rate_limit.py
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 10
    RATE_LIMIT_REGISTER_ATTEMPTS: int = 5

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Database Configuration
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "devtrack"
    DATABASE_URL: Union[str, None] = None

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+psycopg://", 1)
            elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
                url = url.replace("postgresql://", "postgresql+psycopg://", 1)
            return url
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
