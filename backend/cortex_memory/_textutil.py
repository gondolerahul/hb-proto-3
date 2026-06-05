"""
cortex_memory._textutil — small pure text helpers (vendored, host-free).

These are tiny utility functions the CORTEX services use; vendored into the
package so it carries no dependency on the host's ``ai.shared`` utilities.
"""
from __future__ import annotations

import json
from typing import Any


def truncate_for_storage(data: Any, max_chars: int = 400) -> str:
    """Convert any value to a short readable string for episodic storage."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data[:max_chars]
    try:
        s = json.dumps(data, default=str)
    except Exception:
        s = str(data)
    return s[:max_chars]


def parse_json_array(text: str) -> list:
    """Best-effort extraction of a JSON array from LLM text (host-free)."""
    if not text:
        return []
    try:
        import re

        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            val = json.loads(m.group(0))
            return val if isinstance(val, list) else []
    except Exception:
        pass
    return []


def parse_json_object(text: str) -> dict:
    """Best-effort extraction of a JSON object from LLM text (host-free)."""
    if not text:
        return {}
    try:
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            val = json.loads(m.group(0))
            return val if isinstance(val, dict) else {}
    except Exception:
        pass
    return {}


__all__ = ["truncate_for_storage", "parse_json_array", "parse_json_object"]
