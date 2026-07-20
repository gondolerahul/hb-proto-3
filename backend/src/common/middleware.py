import logging

from fastapi import Request, status
from fastapi.responses import Response
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth.models import Company
from src.common.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# C5 — methods that *act*; blocked in read-only (reads/GETs still flow).
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# Paths a read-only tenant may still POST to: pay (clear the lapse), export
# their data, and auth. Everything else agent-facing is blocked.
_READ_ONLY_ALLOWED_PREFIXES = (
    "/api/v1/auth", "/api/v1/billing", "/api/v1/credits",
)


def _read_only_allows(path: str) -> bool:
    return (any(path.startswith(p) for p in _READ_ONLY_ALLOWED_PREFIXES)
            or "export" in path)


def _json_403(detail: str) -> Response:
    return Response(content=f'{{"detail": "{detail}"}}',
                    status_code=status.HTTP_403_FORBIDDEN,
                    media_type="application/json")


class CompanySuspensionMiddleware(BaseHTTPMiddleware):
    """Graduated access control (C5): a lapsed tenant degrades to read-only —
    reads + billing + export still work — before a hard suspend, instead of an
    instant cliff."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (path.startswith("/api/v1/auth") or path == "/"
                or path.startswith("/docs") or path.startswith("/openapi.json")):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                from src.ai.trust.dunning import is_read_only, is_suspended
                from src.common.security import decode_access_token

                payload = decode_access_token(token)
                company_id = payload.get("company_id") if payload else None
                if company_id:
                    async with AsyncSessionLocal() as db:
                        company = (await db.execute(
                            select(Company).where(Company.id == company_id)
                        )).scalar_one_or_none()
                    if company is not None:
                        sub_status = getattr(company, "subscription_status", None) or "current"
                        # Hard block: legacy suspend OR the dunning-suspended state.
                        if company.status == "suspended" or is_suspended(sub_status):
                            return _json_403(
                                "Company is suspended. Please contact support.")
                        # Read-only: block agent-facing mutations, allow reads +
                        # pay + export so the tenant can recover without loss.
                        if (is_read_only(sub_status)
                                and request.method in _MUTATING_METHODS
                                and not _read_only_allows(path)):
                            return _json_403(
                                "Subscription lapsed — account is read-only. "
                                "Reads and exports still work; settle billing to resume.")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Middleware error checking tenant status: {e}")

        return await call_next(request)
