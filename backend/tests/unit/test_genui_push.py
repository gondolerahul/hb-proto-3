"""SEAM T7 — the push sender's laws, without a wire.

The one that matters is the **import boundary**: ``send_tray_push`` may be
referenced by exactly one module outside its own — Pragya's tray delivery
(``genui/channel.py``). That is what turns L8's "only Pragya may push" from
a policy into a build failure: a digest feature, an engagement ping or a
marketing blast would each have to *import the sender*, and this test is
standing in front of the import.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]

#: The single permitted caller (T8's channel), plus the module itself.
ALLOWED_SENDER_SITES = {
    "src/ai/genui/push.py",
    "src/ai/genui/channel.py",
}


def test_the_sender_has_exactly_one_permitted_import_site():
    referencing = set()
    for path in (BACKEND_ROOT / "src").rglob("*.py"):
        rel = str(path.relative_to(BACKEND_ROOT))
        if "send_tray_push" in path.read_text(encoding="utf-8"):
            referencing.add(rel)
    assert referencing <= ALLOWED_SENDER_SITES, (
        f"send_tray_push referenced outside the single-writer set: "
        f"{sorted(referencing - ALLOWED_SENDER_SITES)} — L8 permits only "
        "Pragya's tray delivery to reach a device")


def test_the_payload_is_a_tray_and_nothing_else():
    """The sender's payload is built inline from exactly tray_id and
    one_sentence — no digest field, no count, no deep link farm. Pinned on
    the source so adding a field is a visible, reviewed act."""
    source = (BACKEND_ROOT / "src/ai/genui/push.py").read_text(encoding="utf-8")
    match = re.search(r"payload = json\.dumps\((\{[^}]*\})\)", source)
    assert match, "the sender must build its payload inline"
    assert match.group(1).replace(" ", "").replace("\n", "") == (
        '{"tray_id":tray_id,"one_sentence":one_sentence}')


def test_the_wire_rides_an_injectable_transport():
    """No test may reach a live push service (the FLEET/TWIN/LIB rule):
    the pywebpush import lives inside the default transport, never at
    module scope."""
    source = (BACKEND_ROOT / "src/ai/genui/push.py").read_text(encoding="utf-8")
    module_scope = [
        line for line in source.splitlines()
        if line.startswith(("import ", "from ")) and "pywebpush" in line]
    assert module_scope == []
