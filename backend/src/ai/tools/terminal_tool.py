"""
TerminalTool — Shell command execution for AI agents.

Executes shell commands in an isolated asyncio subprocess, reusing the
sandbox infrastructure patterns from SandboxCodeTool.

Safety features:
  - Hard timeout (default 30s, max 120s)
  - Stdout capped at 8192 characters
  - Stderr captured and returned alongside exit code
  - Minimal environment (no inherited secrets)
  - Command blocklist prevents destructive system commands

Input schema (JSON string):
    {
        "command":     "ls -la /tmp",
        "working_dir": "/tmp",          # optional, defaults to /tmp
        "timeout_s":   30               # optional, max 120
    }

Output (JSON string):
    {
        "exit_code":   0,
        "stdout":      "...",
        "stderr":      "",
        "timed_out":   false
    }
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety: command blocklist patterns
# ---------------------------------------------------------------------------
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+.*-\s*[^\s]*r[^\s]*f\s+/\s*$"),   # rm -rf /
    re.compile(r"\brm\s+.*-\s*[^\s]*f[^\s]*r\s+/\s*$"),   # rm -fr /
    re.compile(r"\bmkfs\b"),                                # mkfs
    re.compile(r"\bdd\s+.*of\s*=\s*/dev/"),                 # dd of=/dev/...
    re.compile(r":\(\)\s*\{"),                              # fork bomb
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bhalt\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\binit\s+0\b"),
    re.compile(r"\binit\s+6\b"),
    re.compile(r">\s*/dev/sd[a-z]"),                        # overwrite disk
    re.compile(r"\bchmod\s+.*777\s+/\s*$"),                 # chmod 777 /
]

_MAX_OUTPUT_CHARS = 8192
_DEFAULT_TIMEOUT_S = 30
_MAX_TIMEOUT_S = 120


def _is_blocked(command: str) -> bool:
    """Check if a command matches any blocked pattern."""
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(command):
            return True
    return False


class TerminalTool(Tool):
    """
    Execute shell commands in a sandboxed subprocess.

    Unlike SandboxCodeTool (which writes code to a temp file and runs an
    interpreter), this tool passes the command string directly to
    ``/bin/bash -c "<command>"``, mirroring how a real terminal works.
    Output is returned as structured JSON with exit_code, stdout, and stderr.
    """

    name = "terminal"
    description = (
        "Execute a bash/shell command in an isolated subprocess. "
        "Input must be a JSON string with a 'command' field containing "
        "the shell command to run. Optional 'working_dir' sets the "
        "working directory (default /tmp). Optional 'timeout_s' "
        "overrides the 30-second default (max 120). "
        "Returns JSON with exit_code, stdout, stderr, and timed_out fields."
    )

    async def run(self, input_data: str) -> str:
        """Execute command and return structured JSON result."""
        return await self._execute(input_data, context=None)

    async def run_with_context(
        self, input_data: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        return await self._execute(input_data, context=context)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _execute(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        # 1. Parse input — supports JSON or raw command text as fallback
        args = None
        try:
            if isinstance(input_data, dict):
                args = input_data
            else:
                args = json.loads(input_data)
        except (json.JSONDecodeError, TypeError):
            pass  # Fall through to raw-text handling below

        if args and isinstance(args, dict):
            command = args.get("command", "").strip()
            working_dir = args.get("working_dir", "/tmp").strip() or "/tmp"
            timeout_s = min(
                int(args.get("timeout_s", _DEFAULT_TIMEOUT_S)),
                _MAX_TIMEOUT_S,
            )
        else:
            # Raw text fallback — treat the entire input as a bash command
            raw_text = input_data if isinstance(input_data, str) else str(input_data)
            raw_text = raw_text.strip()

            # Strip markdown code fences if present (```bash\n...\n```)
            import re
            fence_match = re.search(r'```(?:\w*)\s*\n(.*?)```', raw_text, re.DOTALL)
            if fence_match:
                command = fence_match.group(1).strip()
            else:
                command = raw_text

            working_dir = "/tmp"
            timeout_s = _DEFAULT_TIMEOUT_S
            logger.info(f"TerminalTool: raw text fallback — treating input as command ({len(command)} chars)")

        # P3 — Tenant-scoped working directory for filesystem isolation
        company_id = context.get("company_id") if context else None
        if company_id:
            import os
            scoped_dir = os.path.join("/tmp", "sandbox", str(company_id))
            os.makedirs(scoped_dir, exist_ok=True)
            # Provision shared resources (e.g. Document Factory scripts)
            from src.ai.tools.sandbox_provision import provision_sandbox
            provision_sandbox(scoped_dir)
            # If caller didn't specify a custom working_dir, use the scoped one
            if working_dir == "/tmp":
                working_dir = scoped_dir
            logger.info(f"TerminalTool: executing command for company {company_id}")

        # 2. Validate
        if not command:
            return json.dumps({"error": "'command' field is empty or missing."})

        if _is_blocked(command):
            return json.dumps({
                "error": (
                    "Command blocked by safety filter. "
                    "Destructive system commands are not permitted."
                )
            })

        # 2b. Snapshot existing files before execution (for artifact detection)
        pre_existing_files = set()
        if company_id and working_dir and working_dir != "/tmp":
            try:
                for root, _, files in os.walk(working_dir):
                    for fn in files:
                        pre_existing_files.add(os.path.join(root, fn))
            except OSError:
                pass

        # 3. Execute
        try:
            result = await self._run_subprocess(command, working_dir, timeout_s)
        except Exception as exc:
            logger.error(f"TerminalTool unexpected error: {exc}", exc_info=True)
            return json.dumps({
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Unexpected sandbox failure: {exc}",
                "timed_out": False,
            })

        # 4. Post-execution: detect new document files and register as artifacts
        if company_id and working_dir and working_dir != "/tmp" and pre_existing_files is not None:
            artifact_report = await self._register_new_artifacts(
                working_dir, pre_existing_files, str(company_id), context
            )
            if artifact_report:
                # Append artifact report to the JSON result
                try:
                    result_dict = json.loads(result)
                    result_dict["artifacts"] = artifact_report
                    result = json.dumps(result_dict, default=str)
                except (json.JSONDecodeError, TypeError):
                    result = result + "\n\n" + artifact_report

        return result

    async def _run_subprocess(
        self, command: str, working_dir: str, timeout_s: int
    ) -> str:
        """Spawn bash -c subprocess, capture output, enforce timeout."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash", "-c", command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                # Sandbox env — LibreOffice needs SAL_USE_VCLPLUGIN for headless
                env={
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "HOME": "/tmp",
                    "TMPDIR": "/tmp",
                    "LANG": "C.UTF-8",
                    "SAL_USE_VCLPLUGIN": "svp",  # LibreOffice headless rendering
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
                return json.dumps({
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout_s} seconds.",
                    "timed_out": True,
                })

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Truncate long output
            if len(stdout) > _MAX_OUTPUT_CHARS:
                stdout = (
                    stdout[:_MAX_OUTPUT_CHARS]
                    + f"\n... [truncated, {len(stdout)} total chars]"
                )
            if len(stderr) > _MAX_OUTPUT_CHARS:
                stderr = (
                    stderr[:_MAX_OUTPUT_CHARS]
                    + f"\n... [truncated, {len(stderr)} total chars]"
                )

            return json.dumps({
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": False,
            })

        except FileNotFoundError:
            return json.dumps({
                "exit_code": -1,
                "stdout": "",
                "stderr": "/bin/bash not found on this system.",
                "timed_out": False,
            })
        except Exception as exc:
            return json.dumps({
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Subprocess launch failed: {exc}",
                "timed_out": False,
            })

    # ------------------------------------------------------------------
    # Document file extensions that should be auto-registered as artifacts
    # ------------------------------------------------------------------
    _ARTIFACT_EXTENSIONS = {
        ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "documents"),
        ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "documents"),
        ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "documents"),
        ".pdf":  ("application/pdf", "documents"),
        ".csv":  ("text/csv", "documents"),
        ".json": ("application/json", "documents"),
        ".html": ("text/html", "documents"),
        ".png":  ("image/png", "images"),
        ".jpg":  ("image/jpeg", "images"),
        ".svg":  ("image/svg+xml", "images"),
    }

    async def _register_new_artifacts(
        self, sandbox_dir: str, pre_existing_files: set, company_id: str, context
    ) -> str:
        """Detect new document files and register as artifacts."""
        from uuid import UUID as _UUID
        import os as _os

        new_files = []
        try:
            for root, _, files in _os.walk(sandbox_dir):
                rel_root = _os.path.relpath(root, sandbox_dir)
                if any(s in rel_root for s in ("venv", "__pycache__", "node_modules", "scripts", ".git")):
                    continue
                for fn in files:
                    full_path = _os.path.join(root, fn)
                    if full_path in pre_existing_files:
                        continue
                    ext = _os.path.splitext(fn)[1].lower()
                    if ext in self._ARTIFACT_EXTENSIONS:
                        sz = _os.path.getsize(full_path)
                        if sz >= 100:
                            new_files.append((full_path, fn, ext, sz))
        except OSError:
            return ""

        if not new_files:
            return ""

        registered = []
        try:
            from src.common.database import AsyncSessionLocal
            from src.ai.artifact_service import ArtifactService, ORIGIN_SYSTEM

            async with AsyncSessionLocal() as db:
                art_svc = ArtifactService(db)
                _cid = _UUID(str(company_id))
                for full_path, fn, ext, sz in new_files:
                    mime_type, file_category = self._ARTIFACT_EXTENSIONS[ext]
                    try:
                        with open(full_path, "rb") as f:
                            data = f.read()
                        artifact = await art_svc.save_artifact(
                            file_bytes=data, file_name=fn, mime_type=mime_type,
                            file_category=file_category, origin=ORIGIN_SYSTEM,
                            company_id=_cid, purpose="Auto-generated by terminal execution",
                            generated_by="terminal",
                        )
                        registered.append(f"  • {fn} ({sz:,} bytes) — [Download](/api/v1/artifacts/{artifact.id}/download)")
                        logger.info(f"TerminalTool: auto-registered artifact '{fn}' ({sz} bytes) → {artifact.id}")
                    except Exception as e:
                        logger.warning(f"TerminalTool: failed to register artifact '{fn}': {e}")
        except Exception as e:
            logger.warning(f"TerminalTool: artifact registration failed: {e}")
            return ""

        if not registered:
            return ""
        return "📎 **Generated Artifacts:**\n" + "\n".join(registered)

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The shell command to execute, e.g. 'ls -la' or "
                            "'cat /etc/hostname'"
                        ),
                    },
                    "working_dir": {
                        "type": "string",
                        "description": (
                            "Working directory for the command (default: /tmp)"
                        ),
                        "default": "/tmp",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": (
                            "Execution timeout in seconds (default 30, max 120)"
                        ),
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        }
