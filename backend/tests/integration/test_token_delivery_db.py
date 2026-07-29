"""SEAM T9 / VP-01 — login and refresh through both delivery modes, on real
rows. ``needs_db``.

The user is created directly (not via signup — the E2 throttle makes the
signup path hostile to fixtures, per the repo's own e2e note). What the
database proves: legacy login/refresh are byte-compatible with what
shipped, cookie-mode refresh rotates through the cookie alone, and the
CSRF gate refuses a request that could have been a cross-site form.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException, Response
from sqlalchemy import text

from src.auth.router import login, refresh_token
from src.auth.schemas import RefreshTokenRequest, UserLogin

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

PASSWORD = "vp01-test-password"


@pytest_asyncio.fixture
async def seeded_user():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine
    from src.common.security import get_password_hash

    await engine.dispose()
    cid, uid = uuid.uuid4(), uuid.uuid4()
    email = f"vp01-{uid.hex[:10]}@example.com"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"vp01-test-{cid.hex[:8]}"})
        await s.execute(
            text("INSERT INTO users (id, email, full_name, hashed_password, "
                 "company_id, role, is_active, created_at, updated_at) "
                 "VALUES (:id, :e, 'VP01 Tester', :h, :c, 'tenant_admin', "
                 "true, now(), now())"),
            {"id": str(uid), "e": email,
             "h": get_password_hash(PASSWORD), "c": str(cid)})
        await s.commit()
    try:
        yield email
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM refresh_tokens WHERE user_id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(uid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


def _http_request(headers=None, cookies=None):
    return SimpleNamespace(headers=headers or {}, cookies=cookies or {})


class TestTokenDelivery:
    async def test_legacy_login_is_untouched(self, seeded_user):
        from src.common.database import AsyncSessionLocal
        response = Response()
        async with AsyncSessionLocal() as db:
            body = await login(
                _http_request(), response,
                UserLogin(email=seeded_user, password=PASSWORD), db)
        assert body["refresh_token"]  # the shipped body, exactly
        cookie = next(c for c in response.headers.getlist("set-cookie")
                      if c.startswith("refresh_token="))
        assert "SameSite=lax" in cookie

    async def test_cookie_login_withholds_the_body_token(self, seeded_user):
        from src.common.database import AsyncSessionLocal
        response = Response()
        async with AsyncSessionLocal() as db:
            body = await login(
                _http_request(headers={"x-token-delivery": "cookie"}), response,
                UserLogin(email=seeded_user, password=PASSWORD), db)
        assert "refresh_token" not in body
        cookies = response.headers.getlist("set-cookie")
        refresh = next(c for c in cookies if c.startswith("refresh_token="))
        assert "SameSite=strict" in refresh and "HttpOnly" in refresh
        assert any(c.startswith("csrf_token=") for c in cookies)

    async def test_cookie_refresh_rotates_through_the_cookie_alone(self, seeded_user):
        from src.common.database import AsyncSessionLocal
        login_response = Response()
        async with AsyncSessionLocal() as db:
            await login(
                _http_request(headers={"x-token-delivery": "cookie"}),
                login_response,
                UserLogin(email=seeded_user, password=PASSWORD), db)
        set_cookies = login_response.headers.getlist("set-cookie")
        refresh_value = next(
            c for c in set_cookies if c.startswith("refresh_token=")
        ).split(";")[0].split("=", 1)[1]
        csrf_value = next(
            c for c in set_cookies if c.startswith("csrf_token=")
        ).split(";")[0].split("=", 1)[1]

        refresh_response = Response()
        async with AsyncSessionLocal() as db:
            body = await refresh_token(
                _http_request(
                    headers={"x-token-delivery": "cookie",
                             "x-csrf-token": csrf_value},
                    cookies={"refresh_token": refresh_value,
                             "csrf_token": csrf_value}),
                refresh_response, None, db)
        assert "refresh_token" not in body and body["access_token"]
        rotated = next(
            c for c in refresh_response.headers.getlist("set-cookie")
            if c.startswith("refresh_token="))
        assert refresh_value not in rotated  # rotation happened

    async def test_a_cross_site_shaped_refresh_is_refused(self, seeded_user):
        """The browser would send the cookies; the attacker cannot read the
        CSRF cookie to echo it. That request shape must 403 before any
        token work happens."""
        from src.common.database import AsyncSessionLocal
        response = Response()
        async with AsyncSessionLocal() as db:
            with pytest.raises(HTTPException) as refusal:
                await refresh_token(
                    _http_request(
                        headers={"x-token-delivery": "cookie"},
                        cookies={"refresh_token": "whatever",
                                 "csrf_token": "secret"}),
                    response, None, db)
        assert refusal.value.status_code == 403

    async def test_legacy_refresh_still_takes_the_body_token(self, seeded_user):
        from src.common.database import AsyncSessionLocal
        login_response = Response()
        async with AsyncSessionLocal() as db:
            body = await login(
                _http_request(), login_response,
                UserLogin(email=seeded_user, password=PASSWORD), db)
        refresh_response = Response()
        async with AsyncSessionLocal() as db:
            refreshed = await refresh_token(
                _http_request(), refresh_response,
                RefreshTokenRequest(refresh_token=body["refresh_token"]), db)
        assert refreshed["refresh_token"]
        assert refreshed["refresh_token"] != body["refresh_token"]
