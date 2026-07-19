"""ai.tools.sandbox.tenant_db_manager — per-tenant Postgres container (§23.4).

The prod backend for the tenant data plane: one dedicated ``hb-tenant-db``
(postgres + pgvector) container per company, data directory on a persistent
host volume, tiered hibernation for free-tier economics. Mirrors
:class:`TenantSandboxManager`'s docker-CLI lifecycle (create/reuse/pause/
resume/destroy) — no docker SDK dependency.

Lifecycle (§23.4): the container starts lazily on first activity (``ensure``
returns a ready connection URL) and hibernates after a per-tier idle window
(the ``tenant_db_hibernation`` cron). Cold-start latency is acceptable because
the §18 dispatcher **parks, never drops**, signals for a waking tenant.

Go-live is ops, like the sandbox: build + CVE-scan + registry-publish the
image, then flip ``TENANT_DB_BACKEND=container``. Until then the schema backend
is the default and this manager is dormant.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.common.config import settings

logger = logging.getLogger(__name__)

_LABEL = "hb-tenant-db"
_PGUSER = "hb"
_PGDB = "tenant"


class TenantDBDockerError(RuntimeError):
    pass


@dataclass
class TenantDBConfig:
    image: str = ""
    shared_buffers: str = ""
    password: str = "hbtenant"  # per-container; DB is bound to 127.0.0.1 only

    def __post_init__(self) -> None:
        self.image = self.image or settings.TENANT_DB_IMAGE
        self.shared_buffers = self.shared_buffers or settings.TENANT_DB_SOLO_SHARED_BUFFERS


def _tenant_db_base_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "tenant-db")


class TenantDatabaseManager:
    """Create/reuse/pause/hibernate one ``hb-tenant-db`` container per company."""

    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, config: Optional[TenantDBConfig] = None) -> None:
        self.config = config or TenantDBConfig()

    @staticmethod
    def container_name(company_id: str) -> str:
        return f"{_LABEL}-{company_id}"

    @classmethod
    def _lock_for(cls, name: str) -> asyncio.Lock:
        lock = cls._locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks[name] = lock
        return lock

    # ------------------------------------------------------------------
    # docker CLI helper (mirrors TenantSandboxManager)
    # ------------------------------------------------------------------

    async def _docker(self, *args: str, timeout: float = 60.0, check: bool = True) -> Tuple[int, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", *args,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise TenantDBDockerError("docker CLI not found on PATH") from exc
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise TenantDBDockerError(f"docker {args[0]} timed out") from exc
        out = out_b.decode("utf-8", errors="replace")
        err = err_b.decode("utf-8", errors="replace")
        rc = proc.returncode if proc.returncode is not None else -1
        if check and rc != 0:
            raise TenantDBDockerError(f"docker {args[0]} failed (rc={rc}): {err.strip()}")
        return rc, out, err

    async def _status(self, name: str) -> Optional[str]:
        rc, out, _ = await self._docker("inspect", "-f", "{{.State.Status}}", name, check=False)
        return out.strip() or None if rc == 0 else None

    async def _host_port(self, name: str) -> Optional[str]:
        rc, out, _ = await self._docker(
            "inspect", "-f",
            '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
            name, check=False,
        )
        return out.strip() or None if rc == 0 else None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def ensure(self, company_id: str) -> str:
        """Return an asyncpg URL to a ready tenant DB, creating/waking as needed."""
        name = self.container_name(company_id)
        async with self._lock_for(name):
            status = await self._status(name)
            if status == "paused":
                await self._docker("unpause", name)
            elif status in {"exited", "created", "dead"}:
                await self._docker("start", name)
            elif status != "running":
                await self._create(company_id, name)
            await self._wait_ready(name)
            port = await self._host_port(name)
            if not port:
                raise TenantDBDockerError(f"no published port for {name}")
        return (f"postgresql+asyncpg://{_PGUSER}:{self.config.password}"
                f"@127.0.0.1:{port}/{_PGDB}")

    async def _create(self, company_id: str, name: str) -> None:
        host_dir = os.path.join(_tenant_db_base_dir(), company_id)
        os.makedirs(host_dir, exist_ok=True)
        await self._docker(
            "run", "-d", "--name", name,
            "--label", f"{_LABEL}=1", "--label", f"{_LABEL}-company={company_id}",
            "-e", f"POSTGRES_USER={_PGUSER}",
            "-e", f"POSTGRES_PASSWORD={self.config.password}",
            "-e", f"POSTGRES_DB={_PGDB}",
            "-v", f"{host_dir}:/var/lib/postgresql/data",
            # Bind to loopback only — the app reaches it on the host.
            "-p", "127.0.0.1::5432",
            "--memory", "512m",
            self.config.image,
            "-c", f"shared_buffers={self.config.shared_buffers}",
            "-c", "max_connections=40",
            timeout=120.0,
        )
        logger.info("created tenant-db container %s", name)

    async def _wait_ready(self, name: str, *, attempts: int = 30) -> None:
        for _ in range(attempts):
            rc, _out, _err = await self._docker(
                "exec", name, "pg_isready", "-U", _PGUSER, "-d", _PGDB, check=False,
            )
            if rc == 0:
                return
            await asyncio.sleep(0.5)
        raise TenantDBDockerError(f"tenant-db {name} not ready after wait")

    async def pause(self, company_id: str) -> None:
        name = self.container_name(company_id)
        if await self._status(name) == "running":
            await self._docker("pause", name, check=False)

    async def destroy(self, company_id: str) -> None:
        await self._docker("rm", "-f", self.container_name(company_id), check=False)

    # ------------------------------------------------------------------
    # hibernation reaper (called from the cron)
    # ------------------------------------------------------------------

    async def list_containers(self) -> List[Tuple[str, str, str]]:
        """(name, state, company_id) for all managed tenant-db containers."""
        rc, out, _ = await self._docker(
            "ps", "-a", "--filter", f"label={_LABEL}=1",
            "--format", "{{.Names}} {{.State}} {{.Label \"" + _LABEL + "-company\"}}",
            check=False,
        )
        if rc != 0:
            return []
        result: List[Tuple[str, str, str]] = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                result.append((parts[0], parts[1], parts[2]))
        return result

    async def hibernate_idle(self, idle_seconds: int) -> int:
        """Pause running containers whose last DB activity is older than the tier
        idle window. Returns the count hibernated. Idle is measured from the
        container's last DB write via ``pg_stat_database`` stats reset time —
        a coarse but dependency-free proxy; the caller supplies the tier window.
        """
        paused = 0
        for name, state, _company in await self.list_containers():
            if state != "running":
                continue
            idle = await self._idle_seconds(name)
            if idle is not None and idle >= idle_seconds:
                rc, _, _ = await self._docker("pause", name, check=False)
                if rc == 0:
                    paused += 1
                    logger.info("hibernated idle tenant-db %s (idle=%ss)", name, idle)
        return paused

    async def _idle_seconds(self, name: str) -> Optional[int]:
        rc, out, _ = await self._docker(
            "exec", name, "psql", "-U", _PGUSER, "-d", _PGDB, "-tAc",
            "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - GREATEST("
            "MAX(stats_reset), now() - interval '999 days')))::int, 0) "
            "FROM pg_stat_database WHERE datname = current_database()",
            check=False,
        )
        if rc != 0:
            return None
        try:
            return int(out.strip())
        except ValueError:
            return None
