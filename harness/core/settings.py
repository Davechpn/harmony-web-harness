from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# pydantic-settings parses .env into this model's fields but does not export
# it to os.environ, while pydantic-ai's model providers read API keys
# directly via os.getenv(). Load .env into the process env so both agree.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

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
