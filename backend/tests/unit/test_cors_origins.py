"""Inc-7 D8 E8 — what the credentialed CORS allow-list may contain.

``allow_credentials=True`` makes every entry in ``allow_origins`` a page that
may make authenticated calls with the browser's cookies attached, so the list
is a security boundary and not configuration. Two things are pinned:

1. **Vihara's dev origin is there**, because the alternative — discovering
   the omission as a browser console error during a wiring session — is how
   this workstream lost a day to the Vite proxy hiding it.
2. **Nothing cross-site is**, which is the E8 ruling in enforceable form:
   Vihara ships **same-origin** behind
   ``deploy/apache/vihara.hirebuddha.com-le-ssl.conf`` (``ProxyPass /api``),
   because the cookie-mode pair VP-01 sets is SameSite=Strict, Secure and
   **host-only** — a `csrf_token` cookie set by another host cannot be read
   by the app's own JavaScript, so the double-submit the refresh route
   demands cannot be satisfied from a different origin. Adding a foreign
   origin here would not fix that; it would only mean weakening VP-01.

Read from source rather than by importing ``src.main`` — the app builds an
engine and mounts three dozen routers, which is a heavy import for a
question about a list literal.
"""
from __future__ import annotations

import ast
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[2]
MAIN = BACKEND_ROOT / "src" / "main.py"

#: Hosts a credentialed origin may belong to: the loopback names a developer
#: serves from, and this deployment's own domain.
OWN_SUFFIXES = ("hirebuddha.com",)
LOOPBACK = {"localhost", "127.0.0.1"}


def _allow_origins() -> list[str]:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "allow_origins" and isinstance(keyword.value, ast.List):
                return [
                    element.value for element in keyword.value.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                ]
    raise AssertionError("no allow_origins list literal found in src/main.py")


def test_viharas_dev_origin_is_allowed():
    origins = _allow_origins()
    assert "http://localhost:4044" in origins
    assert "http://127.0.0.1:4044" in origins


def test_no_credentialed_origin_is_a_stranger():
    """A wildcard, a null origin, or a third-party host on a list served with
    ``allow_credentials=True`` is a session-theft surface, not a config typo."""
    for origin in _allow_origins():
        assert origin not in ("*", "null"), origin
        host = urlparse(origin).hostname or ""
        own = host in LOOPBACK or any(
            host == suffix or host.endswith("." + suffix)
            for suffix in OWN_SUFFIXES)
        # A bare IP is this project's own dev VM, named explicitly rather
        # than admitted by pattern.
        assert own or host == "34.100.230.121", host
