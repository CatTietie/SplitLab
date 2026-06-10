from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://splitlab:splitlab@localhost:5432/splitlab"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me-in-production"

    class Config:
        env_file = ".env"


settings = Settings()
