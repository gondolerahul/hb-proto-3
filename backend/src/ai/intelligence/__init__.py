"""
ai.intelligence — the Intelligence Engine (Increment 5).

The governed model fleet: a versioned, region-tagged, effective-dated
**model registry** (REG / B12), the complexity-scored **router** (RTR),
the **fleet** of open-weight providers behind a conservative allow-list
(FLEET / D5), and the eval **admission gate** every fleet change must pass
(EVX / §22.2-.4).

Import discipline (the VOICE cycle lesson, HANDOFF §5): this package init
re-exports **nothing** that reaches back toward ``ai.llm`` — ``ai.llm.router``
imports *this* package, so ``ai.intelligence`` must never import ``ai.llm``.
Import submodules directly (``from src.ai.intelligence.models import ...``).
"""
