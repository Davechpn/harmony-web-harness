from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    database_url: str = "postgresql+asyncpg://harness:harness@localhost:5432/harness"
    redis_url: str = "redis://localhost:6379"

    logfire_token: str = ""

    harness_secret_key: str = "changeme"
    platform_owner_api_key: str = "changeme"

    nest_app_base_url: str = "http://localhost:3000"
    nest_app_webhook_secret: str = "changeme"

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = "changeme"


settings = Settings()
