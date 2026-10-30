from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/users"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    jwt_ttl_minutes: int = Field(default=30, ge=1)
    cache_ttl: int = Field(default=60, ge=1)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
