from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from pydantic_settings import BaseSettings, SettingsConfigDict

from pathlib import Path

from pydantic import Field

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):
    database_url: str

    jwt_secret: str = Field(min_length=32)

    model_config = SettingsConfigDict(
    env_file=ENV_FILE,
    env_file_encoding="utf-8",
    extra="ignore",
    
)


settings = Settings()
DATABASE_URL = settings.database_url

engine = create_async_engine(DATABASE_URL)

session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass