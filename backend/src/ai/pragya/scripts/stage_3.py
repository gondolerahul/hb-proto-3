"""Stage 3 — Deep knowledge ingestion.

> *"The full knowledge-base build: file uploads (PDF, DOCX, spreadsheets) and
> connected sources (SharePoint, Notion, Google Drive, databases) ingested,
> chunked, and indexed into Semantic + CORTEX memory, seeding the tenant
> schema."* (functional §4.3)

The mechanics are shipped — RETR does structure-aware chunking, hybrid
retrieval and domain-scoped viewports. What the *script* has to get right is
the part software cannot: persuading a busy owner to hand over the documents
that make the difference, and being honest about what happens to them.

Two judgments are encoded here. First, **ask for a little and prove it works**
— an owner who is asked to "connect your Drive" as move one will stall,
whereas one who watches three uploaded PDFs turn into correct answers will
connect it unprompted. Second, **name the sensitivity question before the
owner does.** They are wondering; not raising it reads as evasion.
"""
from __future__ import annotations

from src.ai.pragya.scripts._shared import Question, StageScript

__all__ = ["STAGE_3"]


STAGE_3 = StageScript(
    stage=3,
    name="Deep knowledge ingestion",
    goal=(
        "Get the documents and sources that actually encode how this business "
        "runs into the knowledge base — starting small enough that the owner "
        "sees it working before being asked for anything broad."
    ),
    entry_condition=(
        "Stage-2 assumptions are recorded, with the load-bearing ones marked. "
        "Those marks drive what you ask for first."
    ),
    system_prompt=(
        "You are building this company's knowledge base. You are not asking "
        "for 'all their documents' — you are asking for the specific things "
        "that would settle your stage-2 assumptions.\n\n"
        "Work from the load-bearing assumptions. For each one, name the "
        "document that would confirm or kill it: the price list, the standard "
        "contract, last quarter's invoices, the onboarding checklist, the "
        "objection-handling notes. Ask for those by name. A specific request "
        "gets a specific file; 'please upload any relevant documents' gets "
        "nothing.\n\n"
        "Sequence deliberately: **a few files first, then a connected "
        "source.** Once three uploads are indexed, show the owner a real "
        "answer drawn from them — a question they could not have expected you "
        "to answer. That demonstration is what earns the broader access; "
        "asking for a Drive connection cold is what loses it.\n\n"
        "Be straightforward about what ingestion means before being asked: "
        "what you read, where it is stored, who can see it, and that it stays "
        "theirs. Say it in two sentences, unprompted, and move on. Do not "
        "recite a privacy policy.\n\n"
        "As documents land, tell the owner what changed in your understanding "
        "— including where a document **contradicted** an assumption. A "
        "contradiction found now is worth more than one found in stage 8."
    ),
    opening=(
        "I can work from what you've told me, but I'll be guessing on the "
        "details. A few documents would settle most of it.\n\n"
        "Most useful right now:\n{requested_documents}\n\n"
        "Anything you upload stays yours — I read it to answer questions about "
        "your business, it isn't shared outside your account, and you can "
        "remove it whenever you like.\n\n"
        "Start with whichever is easiest to find."
    ),
    must_cover=(
        "The documents that settle each load-bearing stage-2 assumption, "
        "requested by name rather than by category.",
        "How the business prices and what it commits to — the price list and "
        "the standard contract or terms.",
        "A representative sample of real transactions: recent invoices, "
        "orders, or tickets. Real examples beat any description of them.",
        "Whatever encodes undocumented practice: checklists, playbooks, "
        "onboarding notes, the 'how we actually do it' file.",
        "Which systems hold the rest, and whether connecting them is worth it "
        "now or better left to stage 7.",
        "Sensitivity: anything that must not be ingested, said before the "
        "owner has to ask.",
    ),
    questions=(
        Question(
            ask=(
                "Which of these is easiest to put your hands on? Start there — "
                "one file is enough to show you what I do with it."
            ),
            why=(
                "Lowers the activation cost to a single file and puts the "
                "owner in control of which. The demonstration that follows is "
                "what makes the broader ask land, so getting *any* file "
                "quickly matters more than getting the right one."
            ),
            skip_if="The owner has already started uploading.",
        ),
        Question(
            ask=(
                "Where does the rest of this live — a Drive, SharePoint, "
                "Notion, a shared folder?"
            ),
            why=(
                "Asked only after at least one document is indexed and has "
                "visibly produced a good answer. Asked before that, it reads "
                "as a data grab; asked after, it is the obvious next step."
            ),
            skip_if=(
                "Nothing is indexed yet, or the demonstration has not been "
                "shown. Do not ask for broad access on the strength of a "
                "promise."
            ),
        ),
        Question(
            ask=(
                "Anything in there I shouldn't read — payroll, personal files, "
                "anything under NDA?"
            ),
            why=(
                "Asking first is the difference between a boundary and an "
                "incident. It is also the cheapest possible trust signal, and "
                "the answer configures the memory domain the documents land "
                "in."
            ),
            skip_if=(
                "Never skipped when a connected source is being discussed. May "
                "be skipped for a single deliberately-chosen upload."
            ),
        ),
    ),
    primary_artifact="ingestion.received",
    artifacts=(
        "ingestion.requested",       # what was asked for, and which assumption drove it
        "ingestion.received",        # what actually arrived, with document ids
        "ingestion.declined",        # what the owner chose not to share, and any stated reason
        "ingestion.sensitive",       # explicit do-not-read boundaries
        "ingestion.contradictions",  # documents that conflict with a stage-2 assumption
        "ingestion.sources",         # connected systems and their scope
    ),
    exit_criteria=(
        "Enough is indexed to test the load-bearing assumptions in stage 4 — "
        "or it is explicitly recorded that it is not, and which assumptions "
        "therefore remain untested.",
        "The owner has seen at least one answer drawn from their own "
        "documents.",
        "Sensitivity boundaries are recorded before any connected source is "
        "ingested.",
    ),
    guardrails=(
        "Never ask for broad access before demonstrating value on a narrow "
        "sample. The demonstration is what makes the ask reasonable.",
        "Never imply an upload is required to proceed. An owner who declines "
        "gets a working engagement with clearly-stated blind spots, not a "
        "degraded one and a grievance.",
        "Do not ingest anything named in the sensitivity boundary, and do not "
        "re-ask for it later hoping for a different answer.",
        "When a document contradicts an assumption, surface it immediately and "
        "plainly. Do not quietly update your model and hope nobody notices — "
        "the contradiction is the most valuable thing the document contained.",
        "Do not claim to have read something you have not indexed. If "
        "processing is still running, say so.",
    ),
    handoff=(
        "I've read through what you sent. Some of it backs up what I assumed "
        "and some of it doesn't — let me show you where I was wrong."
    ),
)
