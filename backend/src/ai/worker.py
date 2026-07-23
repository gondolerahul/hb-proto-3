"""
worker.py — Arq worker entrypoint.

This file is intentionally minimal. All execution logic lives in:
  - ai.core.execution_engine   (ExecutionEngine)
  - ai.core.arq_jobs           (job functions)
  - ai.core.prompt_utils        (parse_variables, build_sandwich_prompt, etc.)
  - ai.core.context_utils       (store_step_output, sanitize_context)
  - ai.core.exceptions          (UncertaintySignal, AgentError, etc.)
  - ai.step_executor            (StepExecutorService)

Only WorkerSettings and cron registration remain here because arq
requires them at module level for worker discovery.

Phase 10A restructuring: decomposed from 1,992 lines → ~80 lines.
"""
from arq.connections import RedisSettings
import logging
import warnings

# Suppress third-party DeprecationWarnings we can't fix (dependency-internal)
warnings.filterwarnings("ignore", message=".*Inheritance class AiohttpClientSession.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*datetime.datetime.utcnow.*", module="sqlalchemy")
warnings.filterwarnings("ignore", message=".*has been renamed to.*ddgs.*", category=RuntimeWarning)

logger = logging.getLogger(__name__)

# --- Arq job imports (used by WorkerSettings.functions) ---
from src.ai.core.arq_jobs import (
    run_execution_recursive,
    process_gateway_event,
    process_document,
    dreaming_worker,
    dreaming_cron_trigger,
    dreaming_outcome_trigger,
    graph_maintenance_worker,
    resume_execution,
    resume_parent_run,
    cortex_resume_scheduled,
    critic_calibration_job,
    skill_promotion_scan,
    meta_agent_prompt_evolution,
    kpi_rollup_refresh,
    cost_estimator_refresh,
)
from src.ai.campaign_worker import (
    execute_campaign_task,
    pause_campaign_task,
    stop_campaign_task,
)
from src.ai.signals.dispatcher import dispatch_signal
from src.ai.signals.email_poll import email_inbound_poll
from src.ai.signals.sweeper import signal_sweeper
from src.ai.tenant_schema.maintenance import (
    tenant_db_hibernation,
    tenant_db_nightly_backup,
)
from src.ai.loop.heartbeat import loop_heartbeat
from src.ai.loop.watchdog import loop_watchdog
from src.ai.memory.rechunk_cron import chunk_upgrade_sweep
from src.ai.trust.crons import dunning_sweep
from src.ai.governance.crons import demotion_sweep
from src.ai.voice_loop.crons import voice_deferred_reap, voice_deferred_sweep
from src.ai.lead_queue_worker import poll_lead_queue_task

# Register Solo Pack agent tools (Inc 2) on worker boot — the agent loop runs here.
from src.ai.solo_pack.tools import register_solo_pack_tools
register_solo_pack_tools()
# Install the TRUST consent registry into the KAR outbound seam (Inc 2 / D6).
from src.ai.trust.consent_registry import install_consent_registry
install_consent_registry()
# Install the CONN+SOR connector-backed write-back provider into the SOR seam (Inc 4).
from src.ai.connectors.writeback import install_connector_writeback
install_connector_writeback()

# Model imports needed by arq at module scope
from src.common.database import AsyncSessionLocal  # noqa: F401


# ---------------------------------------------------------------------------
# Arq WorkerSettings
# ---------------------------------------------------------------------------

# Intended dedicated queue for async child runs, so a fan-out PROCESS can't
# starve top-level runs (and vice-versa). NOT routed yet: enqueuing children
# here requires deploying a worker bound to this queue, otherwise children
# would never be consumed. Until that worker exists, child dispatch stays on
# the default queue and load is bounded by governance.max_concurrent_children
# (see ChildEntityExecutor). Wire this in the C4 chain alongside the deletion.
CHILD_RUN_QUEUE = "children"


class WorkerSettings:
    functions = [
        run_execution_recursive,
        process_gateway_event,
        process_document,
        execute_campaign_task,
        pause_campaign_task,
        stop_campaign_task,
        resume_execution,
        resume_parent_run,
        # Outcome-triggered Dreaming.
        dreaming_outcome_trigger,
        # Signal bus (Increment 1 / SIG).
        dispatch_signal,
    ]
    # Register CORTEX scheduled wake-up cron
    cron_jobs = [
        # Run every 5 minutes to check for scheduled tree resumptions
        # arq expects: cron(coroutine, minute=set, hour=set, ...)
    ]

    job_timeout = 7200  # 2-hour absolute ceiling; per-entity timeout via logic_gate config

    # Parse Redis URL from environment config
    @staticmethod
    def _parse_redis_url():
        from src.common.config import settings
        from urllib.parse import urlparse
        parsed = urlparse(settings.REDIS_URL or "redis://localhost:6379")
        return parsed.hostname or "localhost", parsed.port or 6379

    _host, _port = _parse_redis_url.__func__()
    redis_settings = RedisSettings(host=_host, port=_port)


try:
    from arq.cron import cron
    WorkerSettings.cron_jobs = [
        cron(cortex_resume_scheduled, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        # C: Auto-schedule dreaming every 6 hours
        cron(dreaming_cron_trigger, hour={0, 6, 12, 18}, minute={15}),
        # Weekly critic calibration (Sunday 03:15 UTC)
        cron(critic_calibration_job, weekday=6, hour=3, minute=15),
        # Weekly skill candidate scan (Sunday 04:30 UTC)
        cron(skill_promotion_scan, weekday=6, hour=4, minute=30),
        # Weekly Meta-Agent prompt-evolution candidates
        # (Monday 05:00 UTC; never auto-applies — HITL gate required).
        cron(meta_agent_prompt_evolution, weekday=0, hour=5, minute=0),
        # Hourly KPI rollup refresh (xx:07 to spread
        # load away from other top-of-hour crons).
        cron(kpi_rollup_refresh, minute={7}),
        # /9: Nightly cost-estimator baseline refresh from
        # telemetry (02:30 UTC — quiet hour, follows the daily aggregate).
        cron(cost_estimator_refresh, hour=2, minute=30),
        # Signal-bus sweeper: every minute — re-dispatch stale PENDING,
        # review PARKED, drive retry backoff (Inc 1 / SIG §18.2–.3).
        cron(signal_sweeper, minute=set(range(60))),
        # Inbound email poll → email.inbound signals (subscription-gated).
        cron(email_inbound_poll, minute={m for m in range(0, 60, 2)}),
        # Tenant-DB hibernation (container backend only; no-op on schema).
        cron(tenant_db_hibernation, minute={m for m in range(0, 60, 5)}),
        # Nightly per-tenant backup (03:40 UTC — quiet hour).
        cron(tenant_db_nightly_backup, hour=3, minute=40),
        # Loop heartbeat scan (every minute; per-Loop pacing is heartbeat_interval_s).
        cron(loop_heartbeat, minute=set(range(60))),
        # Loop watchdog: flag stalled heartbeats (every 2 minutes).
        cron(loop_watchdog, minute={m for m in range(0, 60, 2)}),
        # Dunning ladder sweep (TRUST C5) — daily at 01:10 UTC, after the
        # midnight daily-credit job so a tenant's ladder position reflects the
        # day it just entered.
        cron(dunning_sweep, hour=1, minute=10),
        # Lazy chunk upgrade (RETR T2) — a small batch hourly at :35. No
        # deadline; it shares the embedding rate limit with live ingestion,
        # which must win, and parks at B13's platform cap.
        cron(chunk_upgrade_sweep, minute={35}),
        # C4 autonomy demotion (Inc 3) — daily. The observation window is 7
        # days, so a trend cannot change between two minutes; running it on
        # the 60s sweeper would repeat per-agent aggregates 1,440× for the
        # same answer. Sits after the dunning sweep.
        cron(demotion_sweep, hour=1, minute=40),
        # Inc-4 T6 — drain the post-call queue Inc-3 left filling. Small batch,
        # no deadline: a call reflected on an hour late is worth what one
        # reflected on immediately is worth, and the provider rate limit
        # belongs to live conversation.
        cron(voice_deferred_sweep, minute={m for m in range(0, 60, 10)}),
        # ...and reap finished rows, or draining just converts an unbounded
        # queue into an unbounded archive.
        cron(voice_deferred_reap, hour=2, minute=50),
        # Lead queue poller: every minute — pick pending leads and place
        # outbound calls via Tata Tele (CRM lead.created pipeline).
        cron(poll_lead_queue_task, minute=set(range(60))),
    ]
except ImportError:
    pass  # arq.cron may not be available in all versions

