from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_MASTER_KEY: str = "your-default-dev-key-must-be-32-bytes" # Overridden by env
    STREAMING_HOST: str = "localhost:8002"
    STREAMING_PROTOCOL: str = "ws"

    # Phase 12 `02` S4 — per-tenant container sandbox. OFF by default;
    # SubprocessRuntime stays the dev/CI default and the production rollback.
    SANDBOX_CONTAINER_RUNTIME_ENABLED: bool = False
    SANDBOX_IMAGE: str = "hb-sandbox:local"
    SANDBOX_NETWORK: str = "none"
    SANDBOX_MEMORY: str = "1g"
    SANDBOX_CPUS: str = "1.0"
    SANDBOX_PIDS_LIMIT: int = 256
    SANDBOX_IDLE_PAUSE_SECONDS: int = 900
    SANDBOX_REAP_SECONDS: int = 86400
    # S6 cost attribution: sandbox runtime time is metered against this SKU
    # (IntegrationRegistry.service_sku, owned by the APP company; cost_unit
    # "second"). Seed it with scripts/seed_sandbox_sku.py.
    SANDBOX_COST_SKU: str = "sandbox-runtime"
    # S5 persistent browser: when enabled, headless_browser uses a persistent
    # Chromium profile under the tenant workspace so cookies/logins survive across
    # calls. OFF by default (ephemeral context = today's behavior).
    SANDBOX_PERSISTENT_BROWSER_ENABLED: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
