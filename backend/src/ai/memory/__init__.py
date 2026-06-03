"""
ai.memory — CORTEX memory system and all memory domain services.

Domains:
  - Knowledge: Persistent reference KB (documents, ingested content)
  - Experience: Observations and patterns learned from execution
  - Intelligence: Distilled rules, strategies, and preferences
  - Episodic: Raw execution history per entity

Key services:
  - CortexService: Tree CRUD and navigation (Phase 11 Track 0 rename of CortexRouter)
  - CortexBridge: Interface between execution engine and CORTEX
  - MemoryRouter: Legacy 3-tier memory retrieval (v1)
  - MemoryAssemblyService: 4-domain unified retrieval (v2)
"""
from src.ai.memory.cortex_service import CortexService, CortexRouter
from src.ai.memory.cortex_bridge import CortexBridge
from src.ai.memory.memory_service import MemoryRouter
from src.ai.memory.memory_assembly_service import MemoryAssemblyService

__all__ = [
    "CortexService", "CortexRouter",  # CortexRouter is a deprecated alias.
    "CortexBridge",
    "MemoryRouter", "MemoryAssemblyService",
]
