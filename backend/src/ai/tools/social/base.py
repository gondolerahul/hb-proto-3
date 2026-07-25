"""
SocialMediaTool — Abstract base class for all social media AI tools.

Provides shared functionality:
- Credential resolution from social_connections table
- HTTP request helper with retry + error handling
- Standard JSON function schema pattern
"""
import json
import logging
from abc import abstractmethod
from typing import Any, Dict, Optional

import httpx

from src.ai.tools.base import Tool, ToolStatus

logger = logging.getLogger(__name__)

# Default timeout for all social API calls
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 2


class SocialMediaTool(Tool):
    """
    Abstract base class for social media platform tools.

    Subclasses MUST set:
        - name: str
        - description: str
        - platform: str  (e.g. 'linkedin', 'twitter', 'facebook')

    Subclasses implement:
        - _execute(params, credentials, context) -> dict
        - get_function_schema() -> dict
    """

    platform: str = ""  # Override in subclass

    # C8 social audit (Phase 12): the 15 social/ads platform integrations are
    # not yet wired to any production entity and several are unfinished. They
    # are tagged EXPERIMENTAL so they require an explicit per-company opt-in
    # (``tools.experimental.{tool_id}=true``) via
    # ``ToolRegistry.get_visible_tools_for_company`` before an agent can use
    # them. Promote an individual platform to ``ToolStatus.ACTIVE`` on its
    # subclass once it is verified end-to-end. See tools/integrations README.
    status: ToolStatus = ToolStatus.EXPERIMENTAL

    async def run(self, input_data: str) -> str:
        """Delegate to run_with_context (credentials require context)."""
        return await self.run_with_context(input_data, None)

    async def run_with_context(
        self, input_data: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Parse input, resolve credentials, and execute the platform-specific action.
        """
        try:
            params = json.loads(input_data) if isinstance(input_data, str) else input_data
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        # Resolve credentials from social_connections table
        company_id = context.get("company_id") if context else params.get("company_id")
        if not company_id:
            return json.dumps({
                "error": "No company_id in context. Cannot resolve social media credentials."
            })

        from src.ai.social_connection_service import resolve_connection

        credentials = await resolve_connection(
            company_id=company_id,
            platform=self.platform,
            account_name=params.get("account_name"),
            platform_user_id=params.get("platform_user_id"),
        )

        if not credentials or not credentials.get("access_token"):
            return json.dumps({
                "error": (
                    f"No active {self.platform} connection found for this company. "
                    f"Please configure a social connection first via POST /api/social-connections."
                )
            })

        # Inc-6 GATE T3+T4 — the tenant's own consent posture, checked here
        # because every one of the 64 social tools funnels through this method:
        # a platform module added later inherits the check rather than needing
        # to remember it. Separate from the PolicyGate, which has already
        # decided whether the *agent* may act at its band; this decides whether
        # the *tenant* broadcasts on this channel at all.
        from src.ai.trust.broadcast_guard import guard_social_call

        guard = await guard_social_call(self.name, self.platform, company_id, params)
        if not guard.allowed:
            logger.info(
                f"[{self.name}] refused by channel posture for company "
                f"{company_id}: {guard.reason}"
            )
            return json.dumps({
                "error": f"Refused by this tenant's {self.platform} broadcast posture.",
                "reason": guard.reason,
                "refused_by": "channel_posture",
            })
        # Audience filtering rewrites the params rather than refusing the call
        # (decision 5), so execute with the cleaned list, never the original.
        params = dict(guard.params)
        if guard.suppressed_count:
            logger.info(
                f"[{self.name}] {guard.suppressed_count} audience identifier(s) "
                f"suppressed by DNC for company {company_id}"
            )

        try:
            result = await self._execute(params, credentials, context)
            await self._audit_publish(company_id, params, result, guard.suppressed_count)
            return json.dumps(result)
        except httpx.HTTPStatusError as e:
            logger.error(f"[{self.name}] HTTP error: {e.response.status_code} {e.response.text}")
            return json.dumps({
                "error": f"API request failed: {e.response.status_code}",
                "detail": e.response.text[:500],
            })
        except httpx.TimeoutException:
            logger.error(f"[{self.name}] Request timed out")
            return json.dumps({"error": f"{self.platform} API request timed out"})
        except Exception as e:
            logger.error(f"[{self.name}] Execution error: {e}", exc_info=True)
            return json.dumps({"error": f"{self.name} failed: {str(e)}"})

    async def _audit_publish(
        self,
        company_id: Any,
        params: Dict[str, Any],
        result: Dict[str, Any],
        suppressed_count: int,
    ) -> None:
        """Emit ``broadcast.published`` after a successful publish (GATE T6).

        Until GATE, a public post left no trace on the signal bus at all, so
        "what did our agents say in public last week" had no answer. This gives
        it one — including on the platforms nothing polls yet, which is why the
        outbound audit does not wait for the inbound half.

        Never allowed to break a send. The post has already happened by the
        time this runs; raising here would report a failure for something that
        succeeded, and the caller would reasonably retry it — publishing twice.
        A missing audit row is the lesser harm, and it is logged.
        """
        from src.ai.governance.authority import category_for_tool

        if category_for_tool(self.name) != "broadcast":
            return
        if not isinstance(result, dict) or result.get("error"):
            return
        try:
            import uuid as _uuid

            from src.ai.signals.broadcast_inbound import emit_broadcast_published
            from src.common.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await emit_broadcast_published(
                    db,
                    _uuid.UUID(str(company_id)),
                    platform=self.platform,
                    tool_name=self.name,
                    item_id=str(
                        result.get("post_id") or result.get("id")
                        or result.get("video_id") or ""
                    ) or None,
                    permalink=result.get("permalink") or result.get("url"),
                    suppressed_count=suppressed_count,
                )
        except Exception as exc:  # noqa: BLE001 — see the docstring
            logger.warning(
                f"[{self.name}] broadcast.published audit failed for company "
                f"{company_id}: {exc}"
            )

    @abstractmethod
    async def _execute(
        self,
        params: Dict[str, Any],
        credentials: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Platform-specific execution logic.

        Args:
            params: Parsed JSON input from the LLM
            credentials: Decrypted tokens from social_connection_service
            context: Extra execution context (company_id, user_id, etc.)

        Returns:
            Dict with the result to be JSON-serialized back to the LLM
        """
        ...

    # ------------------------------------------------------------------
    # Shared HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _api_request(
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> httpx.Response:
        """
        Make an HTTP request with retry logic.

        Raises httpx.HTTPStatusError on 4xx/5xx responses.
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    resp = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=json_body,
                        params=params,
                        data=data,
                    )
                    resp.raise_for_status()
                    return resp
                except httpx.HTTPStatusError:
                    raise  # Don't retry client errors
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    if attempt == MAX_RETRIES:
                        raise
                    logger.warning(f"[SocialMediaTool] Retry {attempt + 1}/{MAX_RETRIES}: {e}")

    @staticmethod
    def _bearer_headers(access_token: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build standard Bearer token authorization headers."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers
