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
    graph_maintenance_worker,
    resume_execution,
    cortex_resume_scheduled,
)
from src.ai.campaign_worker import (
    execute_campaign_task,
    pause_campaign_task,
    stop_campaign_task,
)

# ---------------------------------------------------------------------------
# Backward-compatibility re-exports
# ---------------------------------------------------------------------------
# These allow existing code to `from src.ai.worker import X` without breaking.
# Deprecated: import from src.ai.core.* directly in new code.
from src.ai.core.execution_engine import ExecutionEngine  # noqa: F401
from src.ai.core.recursive_engine import RecursiveReasoningEngine  # noqa: F401
from src.ai.core.exceptions import UncertaintySignal  # noqa: F401
from src.ai.core.prompt_utils import (  # noqa: F401
    parse_variables,
    build_sandwich_prompt,
    filter_context_for_step,
)
from src.ai.core.context_utils import (  # noqa: F401
    store_step_output as _store_step_output,
    sanitize_context_for_persistence as _sanitize_context_for_persistence,
)
from src.ai.schemas import GoalNode  # noqa: F401
from src.ai.schemas import DEFAULT_REVIEW_SYSTEM_PROMPT as DEFAULT_REVIEW_PROMPT  # noqa: F401
from src.ai.schemas import DEFAULT_PLANNING_SYSTEM_PROMPT as DYNAMIC_PLANNER_PROMPT  # noqa: F401

# Model imports needed by arq at module scope
from src.common.database import AsyncSessionLocal  # noqa: F401


# ---------------------------------------------------------------------------
# Arq WorkerSettings
# ---------------------------------------------------------------------------

class WorkerSettings:
    functions = [
        run_execution_recursive,
        process_gateway_event,
        process_document,
        execute_campaign_task,
        pause_campaign_task,
        stop_campaign_task,
        resume_execution,
    ]
    # Gap #5: Register CORTEX scheduled wake-up cron
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


# Register the cron job after class definition (arq pattern)
try:
    from arq.cron import cron
    WorkerSettings.cron_jobs = [
        cron(cortex_resume_scheduled, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
except ImportError:
    pass  # arq.cron may not be available in all versions
