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

    # ── Increment 1 / SCH — the tenant data plane (technical doc §10.4, §23.4) ──
    # Backend for per-tenant business data. "schema" (default): a per-tenant
    # Postgres schema on the control-plane DB — the dev/CI/test path, zero infra.
    # "container": a dedicated hb-tenant-db container per tenant (prod), managed
    # by TenantDatabaseManager with tiered hibernation. One record-service
    # codepath serves both.
    TENANT_DB_BACKEND: str = "schema"
    TENANT_DB_IMAGE: str = "hb-tenant-db:local"
    # Per-tier idle window before a tenant DB container hibernates (Solo:
    # aggressive; Growth+: always-on = 0 disables). Decision 2026-07-19.
    TENANT_DB_SOLO_IDLE_SECONDS: int = 900        # 15 min
    TENANT_DB_SOLO_SHARED_BUFFERS: str = "256MB"
    TENANT_DB_GROWTH_SHARED_BUFFERS: str = "1GB"
    # Bounded per-tenant engine cache (control-plane pooling keyed by tenant).
    TENANT_DB_ENGINE_CACHE_SIZE: int = 64

    # ── Increment 1 / LOOP+ENV — Loop runtime + budget (technical doc §17, §20.4) ──
    # Single platform heartbeat scan interval; per-Loop pacing is loop_runtime.
    # heartbeat_interval_s. "Simple but configurable" (decision 2026-07-19).
    LOOP_HEARTBEAT_SCAN_SECONDS: int = 60
    LOOP_WATCHDOG_MISS_INTERVALS: int = 3
    # One uniform, configurable default budget envelope (no per-tier defaults in
    # Inc 1; per-tenant override via API). Placeholder until the E1 idle-cost
    # model (Inc 2) derives real numbers.
    LOOP_DEFAULT_ENVELOPE_USD: str = "100.00"
    LOOP_DEFAULT_RESERVE_PCT: int = 10          # protected carve-out (P14/P17)
    LOOP_ENVELOPE_DOWNSHIFT_PCT: int = 80
    # B13 — platform-initiated spend (optimizer/self-healing/meta/sensing) draws
    # from its own capped envelope so it can never starve tenant work.
    LOOP_PLATFORM_ENVELOPE_USD: str = "10.00"
    # C5 — graduated dunning windows (days): full-function grace, then read-only
    # before a hard suspend (decision 1: grace 7d, configurable).
    BILLING_GRACE_DAYS: int = 7
    BILLING_READ_ONLY_DAYS: int = 7
    # E2 — free-credit abuse controls. Daily credits are platform COGS, so they
    # wait for an email verification; tenant creation is capped per origin IP
    # over a rolling 24h. Set the cap to 0 to disable the throttle.
    TRUST_REQUIRE_VERIFIED_FOR_CREDITS: bool = True
    TRUST_SIGNUP_MAX_PER_IP_PER_DAY: int = 3

    # ── B10 — LEARN (Inc-6). Pooled platform learning carries no tenant
    # content by construction (no company column on platform_observations),
    # but a bucket only one tenant contributed to is still attributable by
    # anyone who can read the opt-in list. The floor is applied inside the
    # aggregation job, where company ids are still visible; groups below it
    # are dropped, never deferred.
    LEARN_POOL_MIN_CONTRIBUTORS: int = 3
    # KPI history is a time series and its value is a function of how long it
    # has run. 400 days keeps a full year plus a comparison window; the reaper
    # exists because a store with no reaper is an unbounded archive.
    LEARN_KPI_RETENTION_DAYS: int = 400
    # How far a pooled observation may move a model's *declared* capability
    # profile, on a 0-1 axis. Bounded so a bad week cannot invert the router's
    # ordering — a genuinely bad model is removed by EVX admission, never by
    # score drift. Set to 0.0 to disable observation-corrected routing.
    LEARN_OBSERVATION_WEIGHT: float = 0.2
    # Below this many pooled observations a model gets no correction at all,
    # which is what keeps an empty store from making every model look bad.
    LEARN_OBSERVATION_MIN_SAMPLES: int = 20

    # ── VG-13/VG-14 — LIB (Inc-6). The raw retrieval-usage log is the only
    # unbounded table LIB creates: one row per chunk per retrieval, on every
    # agent answer. 30 days is short because the *rollup* is what is kept —
    # the raw rows exist to be aggregated, not to be an archive.
    #
    # The reaper cannot outrun the rollup whatever this is set to
    # (`library/influence.reap_usage_log` clamps its cutoff), so lowering it
    # cannot cause data loss; it can only fail to free space.
    LIB_USAGE_RETENTION_DAYS: int = 30

    # ── B11 — SEGA (Inc-6). Blast-radius limits on automated self-evolution.
    # A self-heal loop that has found a way to keep proposing is contained by
    # arithmetic rather than by judgement.
    SEGA_MAX_CHANGES_PER_DAY: int = 3
    # The largest share of an entity's runs a canarying change may serve. A
    # "canary" at 80% is a deployment with a reassuring name.
    SEGA_CANARY_FRACTION: float = 0.25
    # An experiment with no end date is not an experiment. An undecided canary
    # past this many days is rolled back, not promoted — the change failed to
    # show it was an improvement, and the burden of proof sits with the change.
    SEGA_CANARY_MAX_DAYS: int = 14

    # ── TWIN (Inc-6) — the Glasshouse. Charter decision 7 made twin spend
    # TENANT-initiated, so every what-if is visibly the tenant's money. These
    # are the bounds that keep it cheap enough to actually use.
    # The default replay window. Short on purpose: most questions a scenario
    # asks are answered by last week, and a wider default would make the
    # common case expensive for the benefit of the rare one.
    TWIN_DEFAULT_WINDOW_DAYS: int = 7
    # The hard cap. A **refusal**, never a truncation — silently shrinking a
    # window would make two runs incomparable without saying so.
    TWIN_MAX_WINDOW_DAYS: int = 30
    # Below this many daily KPI points a forecast is refused outright rather
    # than returned with an interval so wide nobody reads it. A forecast the
    # day after LEARN ships is `unknown`, and it should be.
    TWIN_MIN_SERIES_POINTS: int = 8
    # Per-company daily twin spend. At the cap the shelf **parks** ("resumes
    # tomorrow") rather than failing — the same posture platform work takes.
    TWIN_DAILY_CAP_USD: float = 5.0

    # ── D1 — inward-channel authentication (Inc-3 AUTH, technical §11.3) ──
    # A step-up buys a short window, not a session: every T2/T3 command
    # re-checks at execution time, so this is how long an owner can keep
    # acting on one ceremony, not how long they stay logged in.
    INWARD_AUTH_ELEVATION_MINUTES: int = 10
    # Repeated failed step-ups lock T2+ for the user and alert every
    # registered channel — a spoofer grinding codes is the thing this catches.
    INWARD_AUTH_MAX_FAILED_STEPUPS: int = 5
    INWARD_AUTH_LOCKOUT_MINUTES: int = 15
    # Channel-enrollment OTP and the T3 second-channel nonce.
    INWARD_AUTH_OTP_TTL_MINUTES: int = 10
    INWARD_AUTH_OTP_MAX_ATTEMPTS: int = 5
    INWARD_AUTH_OOB_TTL_MINUTES: int = 10
    # WebAuthn relying party. RP_ID must be the console's registered domain
    # (or a parent of it) and ORIGIN the exact scheme+host the browser sends;
    # a mismatch fails the ceremony closed, which is the intended behaviour.
    WEBAUTHN_RP_ID: str = "localhost"
    WEBAUTHN_RP_NAME: str = "HireBuddha"
    WEBAUTHN_ORIGIN: str = "http://localhost:5173"

    # ── Vihara (Inc-7 SEAM) ───────────────────────────────────────────────
    # Deployment-wide estate clock for the day–night luminance phase. A
    # per-tenant timezone has no home yet (candidate: LEARN's surface.*
    # namespace); until it does, this is deliberately one setting, not a
    # guess per tenant.
    VIHARA_ESTATE_TIMEZONE: str = "UTC"

    # ── Voice call guardrails (Kanakia-Leads-01 fixes) ────────────────────
    # Voicemail detection: disconnect instead of pitching to a mailbox.
    VOICEMAIL_DETECTION_ENABLED: bool = True
    # Outbound call with no lead speech (neither transcript nor audio energy)
    # for this long after the agent's first audio → treated as an answering
    # machine. Must comfortably exceed a polite listen-through of the intro.
    VOICEMAIL_NO_SPEECH_SECONDS: int = 25
    # Voicemail greeting phrases are only scanned during this window from
    # pipeline start; later mentions ("just leave me a message on WhatsApp")
    # are normal conversation.
    VOICEMAIL_PHRASE_WINDOW_SECONDS: int = 30
    # Activity watchdog: no first agent audio within this window of the
    # greeting trigger → pipeline stall, call is torn down as failed.
    VOICE_PIPELINE_STALL_SECONDS: int = 10
    # Both sides idle (no agent audio sent AND no lead speech) for this long
    # → wind-down prompt, then disconnect.
    VOICE_SILENCE_DISCONNECT_SECONDS: int = 15
    # No silence enforcement during the first N seconds of the pipeline
    # (covers setup + greeting latency).
    VOICE_SILENCE_GRACE_SECONDS: int = 20
    # Agent produced no audio for this long after the lead's turn ended →
    # nudge the model; hard-disconnect at 2x only if the flag below is on
    # (tool calls legitimately exceed this window).
    VOICE_AGENT_STALL_SECONDS: int = 10
    VOICE_AGENT_STALL_DISCONNECT: bool = False
    # RMS threshold on 16-bit PCM inbound audio above which the lead counts
    # as speaking (μ-law frames flow continuously even in silence).
    VOICE_VAD_RMS_THRESHOLD: int = 300
    # Echo suppression: while agent audio is playing at the provider, inbound
    # frames quieter than this are NOT forwarded to the model. PSTN echo of
    # the agent's own voice (attenuated, typically rms<600) was triggering
    # Gemini's barge-in and gibberish transcripts; real interjections are
    # much louder. 0 disables the gate.
    VOICE_ECHO_SUPPRESS_RMS: int = 600
    # An interruption only flushes the provider's playback buffer when
    # inbound speech at least this loud was heard in the last ~1.5s —
    # otherwise the "interruption" was echo/noise and wiping the buffer cuts
    # the agent off mid-sentence.
    VOICE_BARGE_IN_RMS_THRESHOLD: int = 1000
    # Agent context cache TTL (seconds); 0 disables. Agent edits take up to
    # this long to reach new calls.
    VOICE_AGENT_CACHE_TTL_SECONDS: int = 300
    # Smartflo login-JWT cache TTL for account APIs (e.g. /v1/call/hangup).
    TATA_AUTH_TOKEN_TTL_SECONDS: int = 43200
    # Country code prepended to 10-digit campaign contact numbers that lack
    # one (Tata rejects non-E.164 numbers with HTTP 422 "Invalid details").
    DEFAULT_PHONE_COUNTRY_CODE: str = "91"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
