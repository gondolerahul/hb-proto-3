"""governance/demotion.py — C4: autonomy demotion triggers (pure policy).

Promotion existed (checkpoint ``before_autonomy_level_promotion``, §9.7
evidence); demotion did not. That asymmetry is what register finding C4 names,
and it matters because §9.7's claim that autonomy is *reversible* is only true
if something actually reverses it. A ladder you can only climb is not a
governance control.

Two decisions shape this module.

**Demotion is automatic; promotion is evidenced.** Falling back a level
happens on a trigger with no human in the loop, because the situations that
warrant it — an agent failing, being blocked repeatedly, drawing complaints —
are exactly the situations where waiting for someone to notice is the problem.
Climbing back up needs a checkpoint and evidence.

**Acceptance rate alone can never justify promotion.** The Blueprint's
"≥98% unedited acceptance" invites rubber-stamping: an owner who approves
everything without reading produces a perfect record for an agent that may be
doing real damage. So ``promotion_evidence_sufficient`` additionally requires
a **random deep-audit sample** — N approvals pulled at random and re-reviewed
blind. If the sample was never taken, the evidence is insufficient by
construction, no matter how good the headline number looks.

Pure: no DB, no clock beyond what is passed in. The sweep in ``crons.py``
gathers the observations and applies the verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.ai.schemas.governance import AutonomyLevel

__all__ = [
    "DemotionTrigger",
    "DemotionThresholds",
    "DEFAULT_THRESHOLDS",
    "AgentObservations",
    "PromotionEvidence",
    "DemotionVerdict",
    "AUTONOMY_LADDER",
    "one_level_down",
    "evaluate_demotion",
    "promotion_evidence_sufficient",
]


#: The ladder, weakest first. Demotion steps exactly one rung.
AUTONOMY_LADDER: tuple[AutonomyLevel, ...] = (
    AutonomyLevel.A0, AutonomyLevel.A1, AutonomyLevel.A2,
    AutonomyLevel.A3, AutonomyLevel.A4,
)


class DemotionTrigger(str, Enum):
    """Why an agent lost a level. Reported to the owner verbatim in stage 9."""

    SLO_BREACH = "slo_breach"
    COMPLAINT_SPIKE = "complaint_spike"
    CRITIC_BLOCK_SURGE = "critic_block_surge"
    HARD_BLOCK_INCIDENT = "hard_block_incident"
    OWNER_COMMAND = "owner_command"
    #: Inc-6 LEARN (B10's drift half): this agent's behaviour moved off its own
    #: trailing baseline and nobody decided it should. LEARN measures and emits
    #: ``learning.drift_detected``; demotion stays here, so there is exactly one
    #: authority that can take a level away.
    BEHAVIOUR_DRIFT = "behaviour_drift"


@dataclass(frozen=True)
class DemotionThresholds:
    """Where each trigger fires.

    ``min_runs`` and ``min_interactions`` exist to stop a single bad day from
    demoting an agent that has barely run: two failures out of three runs is
    noise, not a trend, and an agent demoted on noise teaches the owner to
    ignore demotions.
    """

    min_runs: int = 20
    failure_rate: float = 0.20          # >20% failed runs over the window
    latency_multiple: float = 2.0       # p95 over 2× its sheet's floor
    min_interactions: int = 10
    complaint_rate_multiple: float = 2.0  # complaint rate over 2× baseline
    min_gate_evaluations: int = 20
    gate_block_rate: float = 0.25       # >25% of categorised acts blocked


DEFAULT_THRESHOLDS = DemotionThresholds()


@dataclass(frozen=True)
class AgentObservations:
    """What the sweep measured for one agent over the window."""

    agent_id: str
    display_name: str
    current_level: AutonomyLevel
    runs_total: int = 0
    runs_failed: int = 0
    p95_latency_ms: float | None = None
    latency_floor_ms: float | None = None
    counterparty_interactions: int = 0
    complaints: int = 0
    complaint_baseline_rate: float = 0.0
    gate_evaluations: int = 0
    gate_blocks: int = 0
    hard_block_incidents: int = 0
    owner_demotion_requested: bool = False
    #: Metrics LEARN found off this agent's own baseline in the window (T7).
    #: Names, not numbers: the sweep reports *what* moved so the reason a human
    #: reads is specific, and the judging already happened in `learning/drift`.
    drifted_metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromotionEvidence:
    """The case for raising an agent a level."""

    agent_id: str
    approvals_total: int
    approvals_unedited: int
    #: How many approvals were pulled at random and re-reviewed blind.
    deep_audit_sampled: int
    #: How many of those the auditor judged genuinely correct.
    deep_audit_passed: int
    window_days: int = 30


@dataclass(frozen=True)
class DemotionVerdict:
    """Whether to demote, why, and to what."""

    agent_id: str
    demote: bool
    from_level: AutonomyLevel
    to_level: AutonomyLevel
    triggers: tuple[DemotionTrigger, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def as_sentence(self) -> str:
        """How Pragya reports it — plain, with the cause named."""
        if not self.demote:
            return f"{self.agent_id}: no change ({self.from_level.value})."
        why = "; ".join(self.reasons)
        return (f"{self.agent_id} moved from {self.from_level.value} to "
                f"{self.to_level.value} — {why}.")


def one_level_down(level: AutonomyLevel) -> AutonomyLevel:
    """The next rung down, floored at A0."""
    index = AUTONOMY_LADDER.index(level)
    return AUTONOMY_LADDER[max(0, index - 1)]


def evaluate_demotion(
    obs: AgentObservations,
    thresholds: DemotionThresholds = DEFAULT_THRESHOLDS,
) -> DemotionVerdict:
    """Decide whether ``obs`` warrants demotion. Pure."""
    triggers: list[DemotionTrigger] = []
    reasons: list[str] = []

    # An owner saying "demote X" is authoritative and needs no volume floor.
    if obs.owner_demotion_requested:
        triggers.append(DemotionTrigger.OWNER_COMMAND)
        reasons.append("you asked me to")

    # A hard block is a single event severe enough to act on alone — it means
    # the agent attempted something above its absolute ceiling.
    if obs.hard_block_incidents > 0:
        triggers.append(DemotionTrigger.HARD_BLOCK_INCIDENT)
        reasons.append(
            f"{obs.hard_block_incidents} attempt(s) above the hard-block ceiling")

    if obs.runs_total >= thresholds.min_runs:
        failure_rate = obs.runs_failed / obs.runs_total
        if failure_rate > thresholds.failure_rate:
            triggers.append(DemotionTrigger.SLO_BREACH)
            reasons.append(
                f"{failure_rate:.0%} of runs failed over {obs.runs_total} runs")

        if (obs.p95_latency_ms is not None and obs.latency_floor_ms
                and obs.p95_latency_ms >
                obs.latency_floor_ms * thresholds.latency_multiple):
            triggers.append(DemotionTrigger.SLO_BREACH)
            reasons.append(
                f"p95 latency {obs.p95_latency_ms:.0f}ms against a "
                f"{obs.latency_floor_ms:.0f}ms floor")

    if obs.counterparty_interactions >= thresholds.min_interactions:
        rate = obs.complaints / obs.counterparty_interactions
        ceiling = obs.complaint_baseline_rate * thresholds.complaint_rate_multiple
        # With no baseline yet, any complaint rate above the raw threshold
        # counts — a new agent must not get an unlimited allowance simply
        # because nothing has been measured for it yet.
        effective = ceiling if obs.complaint_baseline_rate > 0 else 0.10
        if rate > effective:
            triggers.append(DemotionTrigger.COMPLAINT_SPIKE)
            reasons.append(
                f"complaints on {rate:.0%} of contacts "
                f"(expected under {effective:.0%})")

    if obs.gate_evaluations >= thresholds.min_gate_evaluations:
        block_rate = obs.gate_blocks / obs.gate_evaluations
        if block_rate > thresholds.gate_block_rate:
            triggers.append(DemotionTrigger.CRITIC_BLOCK_SURGE)
            reasons.append(
                f"{block_rate:.0%} of its governed actions were blocked")

    # Inc-6 LEARN T7. Drift is not a failure — an agent can drift while every
    # SLO holds — so it needs its own branch and its own floor, which
    # `learning/drift` already applied (a baseline of at least three weeks, a
    # 2.5σ step). Repeating a threshold here would be a second opinion on a
    # judgement already made; the trigger is *that* it was made.
    if obs.drifted_metrics:
        triggers.append(DemotionTrigger.BEHAVIOUR_DRIFT)
        reasons.append(
            "behaviour moved off its own baseline: "
            + ", ".join(sorted(obs.drifted_metrics)))

    if not triggers:
        return DemotionVerdict(
            agent_id=obs.agent_id, demote=False,
            from_level=obs.current_level, to_level=obs.current_level,
        )

    target = one_level_down(obs.current_level)
    if target == obs.current_level:
        # Already at A0 — nothing left to take away, but the triggers are
        # still recorded so the owner learns the agent is struggling.
        return DemotionVerdict(
            agent_id=obs.agent_id, demote=False,
            from_level=obs.current_level, to_level=obs.current_level,
            triggers=tuple(triggers),
            reasons=tuple([*reasons, "already at the lowest autonomy level"]),
        )

    return DemotionVerdict(
        agent_id=obs.agent_id, demote=True,
        from_level=obs.current_level, to_level=target,
        triggers=tuple(triggers), reasons=tuple(reasons),
    )


def promotion_evidence_sufficient(
    evidence: PromotionEvidence,
    *,
    min_approvals: int = 50,
    min_unedited_rate: float = 0.98,
    min_sample_rate: float = 0.10,
    min_sample_size: int = 5,
    min_audit_pass_rate: float = 0.95,
) -> tuple[bool, str]:
    """Whether an agent has earned a level. Returns (ok, reason).

    The anti-rubber-stamp rule lives here: a high unedited-acceptance rate is
    **necessary and not sufficient**. Without a random deep-audit sample, an
    owner who approves everything unread produces a flawless record for an
    agent that may be doing real harm, and the number that is supposed to be
    evidence becomes evidence of nothing.
    """
    if evidence.approvals_total < min_approvals:
        return False, (f"only {evidence.approvals_total} approvals so far; "
                       f"{min_approvals} needed before a level is meaningful")

    unedited_rate = evidence.approvals_unedited / evidence.approvals_total
    if unedited_rate < min_unedited_rate:
        return False, (f"unedited acceptance {unedited_rate:.0%}, "
                       f"below the {min_unedited_rate:.0%} bar")

    required_sample = max(min_sample_size,
                          int(evidence.approvals_total * min_sample_rate))
    if evidence.deep_audit_sampled < required_sample:
        return False, (
            f"deep audit covered {evidence.deep_audit_sampled} of a required "
            f"{required_sample}: acceptance rate alone can't support a "
            f"promotion, because approvals may have been rubber-stamped")

    if evidence.deep_audit_sampled == 0:
        return False, "no deep-audit sample was taken"

    audit_rate = evidence.deep_audit_passed / evidence.deep_audit_sampled
    if audit_rate < min_audit_pass_rate:
        return False, (f"deep audit passed {audit_rate:.0%}, below the "
                       f"{min_audit_pass_rate:.0%} bar — the approvals were "
                       f"not as clean as the acceptance rate suggested")

    return True, (f"{unedited_rate:.0%} unedited over "
                  f"{evidence.approvals_total} approvals, with "
                  f"{evidence.deep_audit_sampled} re-audited at "
                  f"{audit_rate:.0%}")
