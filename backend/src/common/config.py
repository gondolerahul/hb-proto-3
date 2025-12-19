from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    ENCRYPTION_MASTER_KEY: str = "your-default-dev-key-must-be-32-bytes" # Overridden by env

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
