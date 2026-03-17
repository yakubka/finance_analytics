"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/analytics"
    database_url_sync: str = "postgresql+psycopg2://postgres:postgres@db:5432/analytics"

    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    csv_path: str = "/app/user_country.csv"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
