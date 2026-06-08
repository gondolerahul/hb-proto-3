"""
ai.tools.sandbox.runtime — the SandboxRuntime boundary (Phase 12 `02` S1/S2).

The sandbox/terminal/browser tools used to each own their subprocess /
Playwright logic. This module introduces a single runtime abstraction they
delegate to, so the *execution substrate* can later be swapped (a persistent
per-tenant Docker `ContainerRuntime`, `02` S4) without touching the tools.

* ``SandboxRuntime`` — the Protocol (exec, file ops, browser session, lifecycle).
* ``ExecResult`` / ``BrowserSession`` — the DTOs the Protocol traffics in.
* ``SubprocessRuntime`` — today's behavior (host asyncio subprocess + a fresh
  Playwright Chromium per session). The default in dev/CI and the production
  rollback path.
* ``get_sandbox_runtime`` — the factory the tools call. Returns
  ``SubprocessRuntime`` until the (S4) ``ContainerRuntime`` lands behind
  ``sandbox.container_runtime_enabled``.

The tools keep their arg-parsing + output-shaping + artifact logic; they hand
the runtime a fully-built argv/env (or browser action) and shape the
``ExecResult`` / page back into their tool contract. Behaviour is unchanged.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass
from typing import (
    Any,
    AsyncIterator,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
)

# Default Chromium context settings — preserved verbatim from the legacy
# HeadlessBrowserTool so SubprocessRuntime is byte-for-byte today's behavior.
_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
    "HireBuddha-AI-Agent/1.0"
)


@dataclass
class ExecResult:
    """Outcome of a single ``SandboxRuntime.exec`` call.

    The runtime captures the raw process result; truncation, JSON/string
    shaping, and error wording are the tool's concern.
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: int = 0
    # Set when the process could not be launched at all (e.g. interpreter
    # missing). ``not_found`` distinguishes FileNotFoundError from other launch
    # failures so the tool can reproduce its exact message.
    launch_error: Optional[str] = None
    not_found: bool = False

    @property
    def ok(self) -> bool:
        return (
            self.returncode == 0
            and not self.timed_out
            and self.launch_error is None
        )


class BrowserSession:
    """A live browser page plus the Playwright objects backing it.

    Yielded by ``SandboxRuntime.open_browser_session``. The tool's action
    methods operate on ``.page``; the runtime owns teardown.
    """

    def __init__(
        self,
        page: Any,
        *,
        _playwright: Any = None,
        _browser: Any = None,
        _context: Any = None,
    ) -> None:
        self.page = page
        self._playwright = _playwright
        self._browser = _browser
        self._context = _context

    async def aclose(self) -> None:
        for closer in (
            getattr(self._context, "close", None),
            getattr(self._browser, "close", None),
            getattr(self._playwright, "stop", None),
        ):
            if closer is None:
                continue
            try:
                await closer()
            except Exception:  # pragma: no cover - best-effort teardown
                pass


@runtime_checkable
class SandboxRuntime(Protocol):
    """The execution substrate the sandbox tools delegate to.

    Two implementations: ``SubprocessRuntime`` (host, today's behavior) and —
    later — ``ContainerRuntime`` (persistent per-tenant Docker, `02` S4). Tool
    code never knows which it got.
    """

    async def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
        env: Optional[Mapping[str, str]] = None,
    ) -> ExecResult:
        """Run ``argv`` to completion (or ``timeout``), capturing stdout/stderr."""
        ...

    def open_browser_session(
        self,
        *,
        timeout_ms: int = 30000,
        viewport: Optional[Mapping[str, int]] = None,
        user_agent: Optional[str] = None,
        persona: Optional[str] = None,
    ) -> "contextlib.AbstractAsyncContextManager[BrowserSession]":
        """Async context manager yielding a ``BrowserSession``."""
        ...

    # --- file ops (host FS today; tenant volume under ContainerRuntime) ---
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def read_file(self, path: str) -> bytes: ...
    async def list_dir(self, path: str) -> List[str]: ...

    # --- lifecycle (no-ops for SubprocessRuntime; real for ContainerRuntime) ---
    async def ensure(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def destroy(self) -> None: ...


class SubprocessRuntime:
    """Today's behavior behind the Protocol: host asyncio subprocesses + a
    fresh ephemeral Playwright Chromium per browser session. No persistence,
    no container — the dev/CI default and the production rollback path."""

    def __init__(self, company_id: Optional[str] = None) -> None:
        self.company_id = company_id

    async def exec(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        timeout: float = 30.0,
        env: Optional[Mapping[str, str]] = None,
    ) -> ExecResult:
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=dict(env) if env is not None else None,
            )
        except FileNotFoundError:
            return ExecResult(
                returncode=-1,
                launch_error=f"{argv[0] if argv else ''} not found",
                not_found=True,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a launch error
            return ExecResult(returncode=-1, launch_error=str(exc))

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout)
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ExecResult(
                returncode=-1,
                timed_out=True,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        return ExecResult(
            returncode=proc.returncode if proc.returncode is not None else -1,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    @contextlib.asynccontextmanager
    async def open_browser_session(
        self,
        *,
        timeout_ms: int = 30000,
        viewport: Optional[Mapping[str, int]] = None,
        user_agent: Optional[str] = None,
        persona: Optional[str] = None,  # noqa: ARG002 - persistence is S5
    ) -> AsyncIterator[BrowserSession]:
        # Imported lazily so the module loads without Playwright; the caller
        # catches ImportError to reproduce the tool's "not installed" message.
        from playwright.async_api import async_playwright

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport=dict(viewport) if viewport else dict(_DEFAULT_VIEWPORT),
            user_agent=user_agent or _DEFAULT_USER_AGENT,
        )
        page = await ctx.new_page()
        page.set_default_timeout(timeout_ms)
        session = BrowserSession(page, _playwright=pw, _browser=browser, _context=ctx)
        try:
            yield session
        finally:
            await session.aclose()

    # --- file ops (thin host-FS wrappers) ---
    async def write_file(self, path: str, content: bytes) -> None:
        with open(path, "wb") as fh:
            fh.write(content)

    async def read_file(self, path: str) -> bytes:
        with open(path, "rb") as fh:
            return fh.read()

    async def list_dir(self, path: str) -> List[str]:
        return os.listdir(path)

    # --- lifecycle: nothing to manage for a host subprocess runtime ---
    async def ensure(self) -> None:
        return None

    async def pause(self) -> None:
        return None

    async def resume(self) -> None:
        return None

    async def destroy(self) -> None:
        return None


def _container_runtime_selected(context: Optional[Mapping[str, Any]]) -> bool:
    """Whether the per-tenant ``ContainerRuntime`` should be used.

    An explicit ``context["container_runtime"]`` wins (this is where a caller
    threads a resolved per-company ``sandbox.container_runtime_enabled`` feature
    flag); otherwise the process-wide ``SANDBOX_CONTAINER_RUNTIME_ENABLED``
    setting decides. Default OFF.
    """
    if context is not None and "container_runtime" in context:
        return bool(context["container_runtime"])
    try:
        from src.common.config import settings

        return bool(settings.SANDBOX_CONTAINER_RUNTIME_ENABLED)
    except Exception:  # noqa: BLE001 - config import must never break tools
        return False


def get_sandbox_runtime(context: Optional[Mapping[str, Any]] = None) -> SandboxRuntime:
    """Return the runtime the sandbox tools should use.

    Defaults to ``SubprocessRuntime`` (today's behavior, the dev/CI default and
    the production rollback path). When the per-tenant container runtime is
    enabled (settings/flag, default OFF) this returns a ``ContainerRuntime``;
    importing it is deferred so a host without Docker support never pays for it,
    and any import failure falls back to ``SubprocessRuntime``. The tools never
    change.
    """
    company_id = None
    if context:
        cid = context.get("company_id")
        company_id = str(cid) if cid else None

    if _container_runtime_selected(context):
        try:
            from src.ai.tools.sandbox.container_runtime import ContainerRuntime

            return ContainerRuntime(company_id=company_id)
        except Exception:  # noqa: BLE001 - never let container selection break a tool
            return SubprocessRuntime(company_id=company_id)

    return SubprocessRuntime(company_id=company_id)
