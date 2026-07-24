"""tests/eval/routing_corpus.py — the curated model-admission exam (EVX, §22.2).

The human-seeded "exam" a candidate model must sit before it may serve. In
production a runner scores the candidate's and the incumbent's outputs on these
cases; here (the tested seam) the ``ModelEval`` fixtures stand in for the
runner's aggregate scores, so the *gate logic* is what the tests exercise. The
exam predates the student: ``INCUMBENT_EVAL`` is captured from the current
version, and the failing-candidate fixtures prove the gate bites.

Mirrors the RETR retrieval goldens (increment-2/06 §T5).
"""
from src.ai.intelligence.admission import ModelEval, SuiteSet

# The task classes a fleet change is evaluated over (the affected classes).
TASK_CLASSES = ("planning", "critic", "extraction", "drafting", "vision", "voice_turn")

# Illustrative curated cases — the exam content (a runner scores models on these).
ROUTING_CORPUS = [
    {"task_class": "planning",
     "prompt": "Draft a 3-step plan to reconcile an overdue invoice.",
     "rubric": "correct ordering; no fabricated steps"},
    {"task_class": "critic",
     "prompt": "Find the flaw in this quote: 3 units @ $40 totalled $100.",
     "rubric": "catches the arithmetic error ($120, not $100)"},
    {"task_class": "extraction",
     "prompt": "Extract the PO number and amount from: 'PO-8841 for $2,300'.",
     "rubric": "exact field values"},
    {"task_class": "drafting",
     "prompt": "Write a one-line polite payment reminder.",
     "rubric": "on-tone; promises nothing not stated"},
]

# The incumbent's captured behaviour (§22.2 — the exam predates the student).
INCUMBENT_EVAL = ModelEval(quality=0.90, cost=0.010)

# Runner fixtures for the admission gate (injected in tests):
GOOD_CANDIDATE = ModelEval(quality=0.91, cost=0.008)        # non-inferior AND cheaper → admit
REGRESSED_CANDIDATE = ModelEval(quality=0.80, cost=0.008)   # quality drop → refuse
EXPENSIVE_CANDIDATE = ModelEval(quality=0.92, cost=0.030)   # >1.5× budget → refuse

# The suites backing a promotion (§22.2):
FULL_SUITES = SuiteSet(incumbent_golden=True, platform_curated=True,
                       self_generated=True, red_teamed=True)
SELF_GENERATED_ONLY = SuiteSet(incumbent_golden=False, platform_curated=False,
                               self_generated=True)
