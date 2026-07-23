"""connectors/credentials.py — encrypt/decrypt a per-company credential set.

A connector credential is not always a bare API key (OAuth connectors carry an
access+refresh token set), so the stored secret is a JSON object encrypted as
one AES-256-GCM blob via the shipped ``common.security`` primitives — the same
master-key path ``config.IntegrationRegistry`` uses. Callers pass and receive a
mapping; the JSON boundary is internal.
"""
from __future__ import annotations

import json
from typing import Any

from src.common.security import decrypt_api_key, encrypt_api_key

__all__ = ["store_secret", "load_secret"]


def store_secret(credentials: dict[str, Any]) -> str:
    """Encrypt a JSON credential set for storage on the binding."""
    return encrypt_api_key(json.dumps(credentials, sort_keys=True))


def load_secret(encrypted: str) -> dict[str, Any]:
    """Decrypt a stored credential set back into a mapping."""
    raw = decrypt_api_key(encrypted)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("connector credential blob did not decode to an object")
    return data
