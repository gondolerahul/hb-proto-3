"""
ai.signals — the Signal Bus & Trigger Registry (Increment 1 / SIG).

Postgres is the bus: signals are transactional rows (outbox pattern)
claimed with ``FOR UPDATE SKIP LOCKED``; Arq is the delivery muscle.
Design: docs/product-road-map/increment-1/01_sig_signal_bus.md
(authority: product_technical_documentation.md §18).
"""
from src.ai.signals.models import Signal, TriggerRegistration

__all__ = ["Signal", "TriggerRegistration"]
