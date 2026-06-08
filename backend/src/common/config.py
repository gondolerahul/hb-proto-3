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
    # S7 egress proxy (Phase 12 `02`/`06`): the network gate for synthesized /
    # network-using tools. When ALLOWLIST is in force the sandbox container joins
    # an --internal docker network (no direct internet) whose only route out is a
    # dual-homed tinyproxy enforcing SANDBOX_EGRESS_ALLOWLIST. OFF by default
    # (NetworkPolicy.NONE → --network none stays today's behavior).
    SANDBOX_EGRESS_PROXY_ENABLED: bool = False
    SANDBOX_EGRESS_IMAGE: str = "hb-egress-proxy:local"
    SANDBOX_EGRESS_NETWORK: str = "hb-egress-internal"
    SANDBOX_EGRESS_UPLINK_NETWORK: str = "hb-egress-uplink"
    SANDBOX_EGRESS_PROXY_PORT: int = 8888
    # Comma-separated host allow-list the proxy permits (suffix match). Default
    # is the Google API surface the tools already depend on.
    SANDBOX_EGRESS_ALLOWLIST: str = "googleapis.com,google.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
