"""
ai.core — Orchestration and execution layer.

Contains the ExecutionEngine, step execution, prompt utilities,
context management, and exception hierarchy.

This is the "brain" of the agentic system, extracted from the
monolithic worker.py during Phase 10A restructuring.
"""

__all__ = [
    "ExecutionEngine",
    "RecursiveReasoningEngine",
    "MetaReviewer",
    "AgentError",
    "UncertaintySignal",
    "CreditExhaustedError",
    "MetaAgentAbort",
    "EntityNotFoundError",
    "CortexError",
    "PlanningError",
    "ToolExecutionError",
    "GoalDriftError",
    "ParallelStepError",
    "StepTimeoutError",
]
