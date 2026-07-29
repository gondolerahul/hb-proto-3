"""VP-01 — cookie-mode token delivery (Inc-7 SEAM T9, D5 §9).

Vihara keeps its access token in memory and takes the refresh token in an
``HttpOnly; Secure; SameSite=Strict`` cookie — so an XSS on the app that
renders generated UI and drives step-up cannot *persist* a stolen session.
The mode is opt-in per caller via the ``X-Token-Delivery: cookie`` header;
**the legacy path is untouched** — no header means exactly the behaviour
that shipped (refresh token in the body, the pre-existing ``lax`` cookie).

Cookie mode changes two things and only two:

* the refresh token is **omitted from the response body** (the body copy is
  the one that ends up in ``localStorage``), and the cookie tightens to
  ``SameSite=Strict``;
* the refresh route takes the token from the cookie and requires a
  **CSRF double-submit**: a non-HttpOnly ``csrf_token`` cookie the client
  echoes back as ``X-CSRF-Token``. A cross-site attacker can make the
  browser *send* the refresh cookie but cannot *read* the CSRF cookie to
  echo it.
"""
from __future__ import annotations

import secrets
from typing import Any, Protocol

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
DELIVERY_HEADER = "x-token-delivery"
REFRESH_MAX_AGE = 7 * 24 * 60 * 60


class RequestLike(Protocol):
    headers: Any
    cookies: Any


def wants_cookie_delivery(request: RequestLike) -> bool:
    return str(request.headers.get(DELIVERY_HEADER, "")).lower() == "cookie"


def set_cookie_mode_cookies(response: Any, refresh_token: str) -> str:
    """The Strict pair: the HttpOnly refresh cookie and the readable CSRF
    cookie. Returns the CSRF value (it is also readable client-side; the
    return is a convenience for tests)."""
    csrf = secrets.token_urlsafe(32)
    response.set_cookie(
        key=REFRESH_COOKIE, value=refresh_token,
        httponly=True, secure=True, samesite="strict",
        max_age=REFRESH_MAX_AGE, path="/api/v1/auth")
    response.set_cookie(
        key=CSRF_COOKIE, value=csrf,
        httponly=False, secure=True, samesite="strict",
        max_age=REFRESH_MAX_AGE, path="/api/v1/auth")
    return csrf


def csrf_ok(request: RequestLike) -> bool:
    """Double-submit: header must equal cookie, and both must exist."""
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    return bool(cookie) and bool(header) and secrets.compare_digest(
        str(cookie), str(header))


def cookie_refresh_token(request: RequestLike) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def token_body(
    access_token: str, refresh_token: str, *, cookie_mode: bool,
) -> dict[str, Any]:
    """The response body: cookie mode omits the refresh token — that copy is
    the one localStorage would keep."""
    if cookie_mode:
        return {"access_token": access_token, "token_type": "bearer"}
    return {"access_token": access_token, "token_type": "bearer",
            "refresh_token": refresh_token}
