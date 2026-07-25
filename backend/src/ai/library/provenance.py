"""library/provenance.py — where a document came from, and whether it is still true.

The vocabularies for the LIB T1 columns on `documents`, kept as data in one
place so a new collection or a new staleness rule is a visible edit rather than
a string typed into a service somewhere.
"""
from __future__ import annotations

import hashlib

__all__ = [
    "SourceKind",
    "SOURCE_KINDS",
    "StalenessState",
    "STALENESS_STATES",
    "content_hash",
]


class SourceKind:
    """A closed set, matching §15.4's collections.

    Closed on purpose: the point of provenance is that every document can
    answer "where did you come from", and an open string field answers it with
    whatever the last caller happened to type.
    """

    #: A human put it there.
    UPLOAD = "upload"
    #: Mirrored from a connected SharePoint / Google Drive / Notion (T7).
    CONNECTED_DRIVE = "connected_drive"
    #: The platform produced it — a report, a generated document (T5).
    GENERATED_ARTIFACT = "generated_artifact"
    #: Distilled out of a conversation rather than filed as a file.
    CONVERSATION_DERIVED = "conversation_derived"


SOURCE_KINDS: frozenset[str] = frozenset({
    SourceKind.UPLOAD,
    SourceKind.CONNECTED_DRIVE,
    SourceKind.GENERATED_ARTIFACT,
    SourceKind.CONVERSATION_DERIVED,
})


class StalenessState:
    """What we believe about whether a document is still true.

    A fact about *our knowledge*, never a claim about the document's content —
    which is why every transition also records a `staleness_reason` in words.
    A flag whose basis is invisible is a flag people learn to dismiss.
    """

    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    SUPERSEDED = "superseded"
    CONTRADICTED = "contradicted"


STALENESS_STATES: frozenset[str] = frozenset({
    StalenessState.FRESH,
    StalenessState.AGING,
    StalenessState.STALE,
    StalenessState.SUPERSEDED,
    StalenessState.CONTRADICTED,
})


def content_hash(text: str) -> str:
    """sha-256 of extracted text — change detection without re-reading.

    Normalised on whitespace first, because a drive sync that re-exports the
    same file with different line endings is not a change and must not trigger
    a re-chunk and a re-embed of the whole document.
    """
    normalised = " ".join((text or "").split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()
