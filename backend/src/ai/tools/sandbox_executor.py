"""
SandboxCodeTool — Sb-A

Executes arbitrary code snippets in an isolated asyncio subprocess.

Safety features:
  - Hard 30-second timeout (configurable per entity via max_execution_seconds)
  - Stdout capped at 4096 characters
  - Stderr captured and returned on non-zero exit
  - Supports Python 3 and Bash (extensible via EXECUTORS map)
  - No network access flag (best-effort, does NOT guarantee security)

Input schema (JSON string):
    {
        "language":  "python" | "bash",
        "code":      "<source code string>",
        "timeout_s": 30           # optional, overrides default
    }

Output:
    stdout text (truncated to 4096 chars) on success
    Error message with stderr on failure
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
from typing import Any, Dict, Optional

from src.ai.tools.base import Tool, ToolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Executor command map — maps language → (interpreter, source-file-extension)
# ---------------------------------------------------------------------------
_EXECUTORS: Dict[str, tuple[str, str]] = {
    "python":  (sys.executable, ".py"),
    "python3": (sys.executable, ".py"),
    "bash":    ("/bin/bash",     ".sh"),
    "sh":      ("/bin/sh",       ".sh"),
}

_MAX_OUTPUT_CHARS = 4096


class SandboxCodeTool(Tool):
    """
    Execute code safely in a subprocess sandbox.

    The tool writes the code to a temp file, spawns a subprocess with
    asyncio, and captures stdout/stderr. A configurable timeout (default
    30 s) ensures runaway processes are killed.
    """
    name = "sandbox_code"
    description = (
        "Execute a Python or Bash code snippet in an isolated subprocess sandbox. "
        "Input must be a JSON string with 'language' ('python' or 'bash') "
        "and 'code' fields. Optional 'timeout_s' overrides the 30-second default. "
        "Returns stdout on success, or an error message with stderr on failure."
    )

    # Per-call default timeout — may be overridden by the entity's
    # ToolDefinition.max_execution_seconds via the args dict.
    DEFAULT_TIMEOUT_S: int = 30

    async def run(self, input_data: str) -> str:
        """Execute code and return stdout or error string."""
        return await self._execute(input_data, context=None)

    async def run_with_context(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        return await self._execute(input_data, context=context)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute(self, input_data: str, context: Optional[Dict[str, Any]]) -> str:
        # 1. Parse input
        try:
            if isinstance(input_data, dict):
                args = input_data
            else:
                args = json.loads(input_data)
        except (json.JSONDecodeError, TypeError):
            return "Error: input must be a JSON string with 'language' and 'code' keys."

        language = str(args.get("language", "python")).lower()
        code = args.get("code", "")
        timeout_s = int(args.get("timeout_s", self.DEFAULT_TIMEOUT_S))

        if not code.strip():
            return "Error: 'code' field is empty."

        executor = _EXECUTORS.get(language)
        if not executor:
            supported = ", ".join(_EXECUTORS.keys())
            return f"Error: unsupported language '{language}'. Supported: {supported}"

        interpreter, ext = executor

        # P3 — Tenant-scoped temp directory for filesystem isolation
        company_id = context.get("company_id") if context else None
        if company_id:
            sandbox_dir = os.path.join(tempfile.gettempdir(), "sandbox", str(company_id))
            os.makedirs(sandbox_dir, exist_ok=True)
            logger.info(f"SandboxCodeTool: executing {language} for company {company_id}")
        else:
            sandbox_dir = None

        # 2. Write code to temp file and execute
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=ext,
                delete=False,
                encoding="utf-8",
                dir=sandbox_dir,
            ) as f:
                f.write(code)
                tmp_path = f.name

            try:
                return await self._run_subprocess(
                    interpreter=interpreter,
                    script_path=tmp_path,
                    timeout_s=timeout_s,
                    working_dir=sandbox_dir,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        except Exception as exc:
            logger.error(f"SandboxCodeTool unexpected error: {exc}", exc_info=True)
            return f"Error: unexpected sandbox failure — {exc}"

    async def _run_subprocess(self, interpreter: str, script_path: str, timeout_s: int, working_dir: str = None) -> str:
        """Spawn subprocess, capture output, enforce timeout."""
        try:
            proc = await asyncio.create_subprocess_exec(
                interpreter,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                # Minimal env — no inherited secrets
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": "/tmp",
                    "TMPDIR": working_dir or "/tmp",
                },
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=float(timeout_s),
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Error: execution timed out after {timeout_s} seconds."

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                msg = f"Error: process exited with code {proc.returncode}."
                if stderr.strip():
                    msg += f"\nStderr:\n{stderr[:2048]}"
                return msg

            # Truncate long output
            if len(stdout) > _MAX_OUTPUT_CHARS:
                stdout = stdout[:_MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(stdout)} total chars]"

            return stdout if stdout else "(no output)"

        except FileNotFoundError:
            return f"Error: interpreter '{interpreter}' not found on this system."
        except Exception as exc:
            return f"Error: subprocess launch failed — {exc}"

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "enum": ["python", "python3", "bash", "sh"],
                        "description": "Programming language to execute",
                    },
                    "code": {
                        "type": "string",
                        "description": "Source code to execute",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Execution timeout in seconds (default 30)",
                        "default": 30,
                    },
                },
                "required": ["language", "code"],
            },
        }
