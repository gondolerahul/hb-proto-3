"""SEAM T9 / VP-01 — cookie-mode token delivery, the pure half.

The property that matters: **the legacy path is untouched.** No header means
exactly the shipped behaviour; the new mode exists only for a caller that
asks for it. And in cookie mode the refresh token must be absent from the
body — the body copy is the one localStorage keeps, which is the whole
finding.
"""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import Response

from src.auth.token_delivery import (
    cookie_refresh_token,
    csrf_ok,
    set_cookie_mode_cookies,
    token_body,
    wants_cookie_delivery,
)


def _request(headers=None, cookies=None):
    return SimpleNamespace(headers=headers or {}, cookies=cookies or {})


# ── mode selection ────────────────────────────────────────────────────────────

def test_no_header_means_the_legacy_path():
    assert wants_cookie_delivery(_request()) is False
    assert wants_cookie_delivery(_request(headers={"x-token-delivery": "body"})) is False


def test_the_header_opts_in_case_insensitively():
    assert wants_cookie_delivery(_request(headers={"x-token-delivery": "cookie"}))
    assert wants_cookie_delivery(_request(headers={"x-token-delivery": "Cookie"}))


# ── the body ─────────────────────────────────────────────────────────────────

def test_cookie_mode_omits_the_refresh_token_from_the_body():
    body = token_body("acc", "ref", cookie_mode=True)
    assert "refresh_token" not in body
    assert body["access_token"] == "acc"


def test_legacy_mode_keeps_the_shipped_body():
    assert token_body("acc", "ref", cookie_mode=False) == {
        "access_token": "acc", "token_type": "bearer", "refresh_token": "ref"}


# ── the cookies ──────────────────────────────────────────────────────────────

def test_the_strict_pair_is_set_and_only_the_csrf_is_readable():
    response = Response()
    csrf = set_cookie_mode_cookies(response, "refresh-value")
    cookies = response.headers.getlist("set-cookie")
    refresh = next(c for c in cookies if c.startswith("refresh_token="))
    csrf_cookie = next(c for c in cookies if c.startswith("csrf_token="))

    assert "HttpOnly" in refresh and "SameSite=strict" in refresh
    assert "Secure" in refresh
    assert "HttpOnly" not in csrf_cookie  # the double-submit leg must be readable
    assert csrf in csrf_cookie


# ── CSRF double-submit ───────────────────────────────────────────────────────

def test_csrf_needs_both_legs_matching():
    ok = _request(headers={"x-csrf-token": "tok"}, cookies={"csrf_token": "tok"})
    assert csrf_ok(ok) is True
    assert csrf_ok(_request(headers={"x-csrf-token": "tok"}, cookies={})) is False
    assert csrf_ok(_request(headers={}, cookies={"csrf_token": "tok"})) is False
    mismatched = _request(
        headers={"x-csrf-token": "a"}, cookies={"csrf_token": "b"})
    assert csrf_ok(mismatched) is False


def test_empty_strings_never_pass_csrf():
    empty = _request(headers={"x-csrf-token": ""}, cookies={"csrf_token": ""})
    assert csrf_ok(empty) is False


def test_the_refresh_cookie_reads_back():
    assert cookie_refresh_token(
        _request(cookies={"refresh_token": "r1"})) == "r1"
    assert cookie_refresh_token(_request()) is None


# ── the cookie paths, which are not symmetrical on purpose ───────────────────

def test_the_csrf_cookie_is_readable_from_the_app_root():
    """R-4 regression. The CSRF cookie shipped scoped to ``/api/v1/auth`` like
    the credential beside it, which made it invisible to ``document.cookie`` on
    a page served from ``/`` — so the client's ``csrfFromCookie`` returned
    ``None``, every refresh went out without ``X-CSRF-Token``, and each reload
    read as an expired session.

    The frontend suite could not catch it: its tests mock the API client, so the
    cookie → header → refresh path had no coverage on either side of the wire.
    It is asserted here, where the cookie is actually set.
    """
    response = Response()
    set_cookie_mode_cookies(response, "refresh-value")
    csrf_cookie = next(
        c for c in response.headers.getlist("set-cookie")
        if c.startswith("csrf_token="))

    assert "Path=/;" in csrf_cookie or csrf_cookie.rstrip().endswith("Path=/")


def test_the_refresh_cookie_stays_pinned_to_the_auth_endpoints():
    """The other half of the asymmetry, and the half that must not drift wider.
    The refresh token IS a credential; pinning its path is most of what cookie
    mode buys. Widening it to ``/`` would attach it to every asset request the
    browser makes.
    """
    response = Response()
    set_cookie_mode_cookies(response, "refresh-value")
    refresh = next(
        c for c in response.headers.getlist("set-cookie")
        if c.startswith("refresh_token="))

    assert "Path=/api/v1/auth" in refresh
