"""Stage 2 — Working assumptions.

> *"From that research she forms an explicit, reviewable hypothesis of the
> tenant's business model, workflows, and processes — tentatively mapped onto
> the 19 canonical Processes. **Assumptions are stated as assumptions, never
> silently treated as facts.**"* (functional §4.3)

The failure mode this stage guards against is the one that makes automation
projects fail late: an early inference hardens into a fact nobody ever
questioned, and six weeks later the configured system is confidently wrong.

The countermeasure is structural. Every assumption is numbered, so it can be
referred to and struck; every assumption carries its **confidence** and the
**evidence** behind it, so the owner can see which ones are load-bearing; and
stage 4 re-tests each one against ingested evidence rather than assuming the
owner caught everything here.
"""
from __future__ import annotations

from src.ai.pragya.scripts._shared import Question, StageScript

__all__ = ["STAGE_2"]


STAGE_2 = StageScript(
    stage=2,
    name="Working assumptions",
    goal=(
        "Put a numbered, confidence-scored hypothesis of how the business runs "
        "in front of the owner, mapped onto the canonical processes, so the "
        "wrong parts can be struck cheaply and early."
    ),
    entry_condition=(
        "Stage 1 produced a research summary the owner has responded to, and "
        "corrections are recorded."
    ),
    system_prompt=(
        "You are drafting a hypothesis of how this business actually operates, "
        "for the owner to correct.\n\n"
        "Write it as a numbered list of assumptions. Each one gets:\n"
        "  - the assumption, in one plain sentence;\n"
        "  - **why you think so** — the specific evidence, from stage-1 "
        "research or the owner's own corrections;\n"
        "  - **how confident you are**, and say it in words a busy person "
        "reads correctly: 'fairly sure', 'a guess', 'inferred from X only'.\n\n"
        "Numbering is not decoration. It lets the owner say 'wrong on 4 and 7' "
        "in five seconds, which is the entire point of this stage.\n\n"
        "Map the assumptions onto the canonical processes — which of them this "
        "business actually runs, which it does not, and which it runs under a "
        "different name. Say the mapping is tentative, because it is.\n\n"
        "Be willing to be wrong in public. An assumption you are 40% sure of, "
        "clearly labelled as such, is far more useful than one you softened "
        "into meaninglessness to avoid being corrected. Hedged mush cannot be "
        "struck, so it survives to mislead stage 6.\n\n"
        "Flag which assumptions are **load-bearing** — the ones where being "
        "wrong changes what gets built. The owner should spend their attention "
        "there, not on the trivia."
    ),
    opening=(
        "Here's how I think {company_name} runs. These are assumptions, not "
        "conclusions — I've numbered them so you can just tell me which ones "
        "are wrong.\n\n"
        "{assumption_list}\n\n"
        "The ones marked ★ are load-bearing: if I've got those wrong, we'd "
        "build the wrong thing. Which numbers should I strike?"
    ),
    must_cover=(
        "The revenue motion end to end: how a stranger becomes a paying "
        "customer, and who touches them at each step.",
        "Which canonical processes this business genuinely runs — including an "
        "explicit list of the ones it does *not*, so absence is a decision "
        "rather than an oversight.",
        "Where the work currently happens: inbox, spreadsheet, WhatsApp, CRM, "
        "someone's head. Be specific; 'a CRM' is not an answer.",
        "Who does what today — which roles exist, and which jobs are one "
        "person's undocumented habit.",
        "The obvious pain: what breaks, what gets dropped, what runs late. "
        "State this as a hypothesis to be confirmed, not a diagnosis.",
        "Which assumptions are load-bearing for the eventual configuration.",
    ),
    questions=(
        Question(
            ask="Which numbers should I strike?",
            why=(
                "Cheapest possible correction interface. It invites deletion "
                "rather than explanation, which is what a busy owner will "
                "actually do; an open 'does this look right?' reliably gets "
                "'looks fine' from someone who skimmed it."
            ),
            skip_if="Never skipped — it is the stage's core move.",
        ),
        Question(
            ask=(
                "On {load_bearing_assumption} — how does that actually work "
                "here today, step by step?"
            ),
            why=(
                "Asked only for load-bearing assumptions, and only where "
                "confidence is low. This is the one place in stage 2 where "
                "spending the owner's time on detail is justified, because the "
                "answer changes what gets built."
            ),
            skip_if=(
                "The assumption is high-confidence, or not load-bearing, or "
                "the owner already corrected it in their first pass."
            ),
        ),
        Question(
            ask=(
                "Anything I've missed entirely — work that happens here that "
                "isn't on this list at all?"
            ),
            why=(
                "Numbered lists bias review toward what is present. Omissions "
                "are invisible to the reviewer unless explicitly invited, and "
                "an omitted process is a process that never gets automated."
            ),
            skip_if=(
                "The owner has already volunteered additions while striking "
                "assumptions."
            ),
        ),
    ),
    primary_artifact="assumptions.list",
    artifacts=(
        "assumptions.list",           # numbered; each with evidence + confidence
        "assumptions.load_bearing",   # the subset that changes the build
        "assumptions.struck",         # what the owner rejected, and why
        "assumptions.process_map",    # tentative mapping onto canonical processes
        "assumptions.additions",      # what the owner said was missing
    ),
    exit_criteria=(
        "Every assumption carries evidence and a confidence level.",
        "The owner has struck, confirmed, or amended each load-bearing "
        "assumption. Silence on a load-bearing assumption is not consent — ask "
        "again, once, before advancing.",
        "The process map names both what applies and what explicitly does not.",
    ),
    guardrails=(
        "Never state an assumption without its evidence. An assumption whose "
        "provenance is 'it seemed likely' is a guess, and should say so.",
        "Do not soften a confident assumption to avoid being wrong, and do not "
        "inflate a weak one to sound authoritative. The confidence label is "
        "the most useful thing on the page.",
        "Do not propose solutions, agents, or bundles yet. The owner has not "
        "finished telling you what is true.",
        "If the owner strikes many assumptions, do not become apologetic or "
        "start hedging everything. Rewrite and move on — being corrected is "
        "the stage working, not failing.",
    ),
    handoff=(
        "Good — that's a much better picture. Now I'd like to read what you "
        "actually run on: documents, records, whatever's lying in a drive. "
        "That's where I'll find out which of these I still have wrong."
    ),
)
