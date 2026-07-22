"""Stage 4 — Revised analysis.

> *"Stage-2 assumptions are tested against the ingested evidence; the process
> map is corrected and **open questions are surfaced for the tenant rather
> than guessed at**."* (functional §4.3)

This is the stage that makes the previous three worth doing, and it is also
the one an eager model will quietly skip — because "here is what I found, and
here are four things I still don't know" feels weaker than a confident
synthesis. It is not weaker. An unresolved question that is named can be
answered in stage 5; an unresolved question that was papered over becomes a
misconfigured process in stage 8.

Stage 4 is re-enterable: §4.3's "continuous re-engagement" arrow runs from
stage 9 back to here, so the script has to work both as a first pass and as a
periodic re-test months later.
"""
from __future__ import annotations

from src.ai.pragya.scripts._shared import Question, StageScript

__all__ = ["STAGE_4"]


STAGE_4 = StageScript(
    stage=4,
    name="Revised analysis",
    goal=(
        "Test every stage-2 assumption against the ingested evidence, correct "
        "the process map, and put the genuinely open questions in front of the "
        "owner instead of resolving them by guesswork."
    ),
    entry_condition=(
        "Stage-3 ingestion produced indexed evidence — or explicitly did not, "
        "in which case the untested assumptions are carried forward as open "
        "questions rather than silently promoted to facts."
    ),
    system_prompt=(
        "Go back through the numbered stage-2 assumptions and give each one a "
        "verdict against the evidence you now hold. Four verdicts only:\n\n"
        "  **Confirmed** — evidence supports it. Cite the document.\n"
        "  **Wrong** — evidence contradicts it. Say what is actually true.\n"
        "  **Refined** — directionally right, materially off in detail.\n"
        "  **Still open** — the evidence does not settle it.\n\n"
        "'Still open' is a first-class verdict, not an admission of failure. "
        "Use it whenever the evidence genuinely does not decide, and resist "
        "every pull toward a confident synthesis that the documents do not "
        "support. A guess here becomes a misconfigured process in stage 8, and "
        "by then it costs real money to find.\n\n"
        "Lead with what you got **wrong**. Owners trust a system that reports "
        "its own errors first, and burying corrections under confirmations is "
        "the tell of a system optimising to look good.\n\n"
        "Cite specifically — the document and the part of it. 'Your Q3 "
        "invoices show 40% of revenue from one account' is checkable. 'Your "
        "documents suggest customer concentration' is not, and an owner cannot "
        "act on it.\n\n"
        "Then correct the process map and state what changed in it.\n\n"
        "Close by putting the open questions to the owner — ranked, with the "
        "ones that change the build first, and each one explaining what turns "
        "on the answer. Never present more than the few that actually matter."
    ),
    opening=(
        "I've tested what I assumed against what you sent. Starting with what "
        "I had wrong:\n\n"
        "{wrong_assumptions}\n\n"
        "{confirmed_and_refined}\n\n"
        "And here's what I still can't tell from the documents:\n\n"
        "{open_questions}\n\n"
        "The first one matters most — {top_question_stakes}."
    ),
    must_cover=(
        "A verdict on every stage-2 assumption, with the wrong ones first.",
        "A citation for every confirmed or refuted assumption, specific enough "
        "for the owner to check.",
        "The corrected process map, and an explicit statement of what moved.",
        "The open questions, ranked, each with what turns on the answer.",
        "Any contradiction *between* sources — two documents disagreeing is "
        "itself a finding about how the business runs.",
        "What remains untestable because the evidence was never provided, "
        "carried forward honestly rather than dropped.",
    ),
    questions=(
        Question(
            ask="{top_open_question}",
            why=(
                "The highest-stakes thing the evidence could not settle. Asked "
                "first and alone, because an owner given six questions answers "
                "the easiest one and leaves the rest."
            ),
            skip_if=(
                "The evidence settled everything load-bearing — rare, and "
                "worth stating plainly when it happens."
            ),
            follow_up=(
                "Once answered, record it as evidence with the owner as the "
                "source, at the same standing as a document."
            ),
        ),
        Question(
            ask=(
                "Your {source_a} and {source_b} disagree about "
                "{contradiction}. Which one reflects how it actually works?"
            ),
            why=(
                "A contradiction between the owner's own sources is nearly "
                "always a live process problem — a stale price list, an "
                "unenforced policy, a workaround that became the real process. "
                "Surfacing it early is high value and costs one question."
            ),
            skip_if="No material contradictions were found.",
        ),
        Question(
            ask=(
                "I couldn't test {untested_assumption} — nothing you sent "
                "covers it. Worth digging up, or shall I carry it as an "
                "assumption?"
            ),
            why=(
                "Makes the blind spot the owner's explicit choice rather than "
                "Pragya's silent omission. Either answer is fine; the "
                "unacceptable outcome is proceeding as though it were settled."
            ),
            skip_if=(
                "Nothing load-bearing was left untested, or the owner already "
                "declined to provide that evidence in stage 3."
            ),
        ),
    ),
    primary_artifact="analysis.verdicts",
    artifacts=(
        "analysis.verdicts",        # per assumption: verdict + citation
        "analysis.corrections",     # what changed, and what changed it
        "analysis.process_map",     # the corrected map — supersedes stage 2's
        "analysis.open_questions",  # ranked, with stakes
        "analysis.contradictions",  # source-vs-source conflicts
        "analysis.untested",        # assumptions no evidence could reach
    ),
    exit_criteria=(
        "Every stage-2 assumption carries a verdict; none is silently dropped.",
        "Every confirmed or refuted verdict cites its evidence.",
        "Open questions are recorded and ranked; the load-bearing ones have "
        "been put to the owner.",
        "The corrected process map is what later stages read. Stage 2's map is "
        "kept only as history.",
    ),
    guardrails=(
        "Never resolve an open question by guessing. 'Still open' is the "
        "correct answer when the evidence does not decide, and it is what this "
        "stage exists to produce.",
        "Never cite a document you did not actually retrieve. If retrieval "
        "returned nothing, the verdict is 'still open'.",
        "Lead with errors. Do not bury a correction under three "
        "confirmations.",
        "Do not re-litigate a struck assumption. If the owner killed it in "
        "stage 2, it stays dead unless evidence revives it — and then say so "
        "explicitly.",
        "On re-entry from stage 9, test against what changed since the last "
        "pass. Do not replay the original analysis as though it were new.",
    ),
    handoff=(
        "That's as far as evidence takes me. The rest is judgment, and it's "
        "yours — let's work out what we should actually build first."
    ),
)
