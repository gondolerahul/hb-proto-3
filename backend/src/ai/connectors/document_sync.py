"""connectors/document_sync.py — connected drives into the Library (LIB T7, VG-14).

**Deliberately not `sync.py`.** That module mirrors *records* and emits
`object.synced`, engaging the Inc-4 mastering machine — write-back-first,
master-wins, the ownership migration. A drive masters no HBS object; it is a
source of documents, not of records. Routing drives through record sync would
have made every mirrored file a candidate for conflict resolution against a
record that does not exist.

**A file deleted at the source is marked `superseded`, never deleted** (decision
3). "Was this true in March?" stays answerable, and a drive misconfiguration
that briefly hides a folder does not silently destroy a tenant's Library.

**Platform-initiated** (decision 6), reusing `CostAttribution.CONNECTOR_SYNC`,
which is already in `PLATFORM_INITIATED_ATTRIBUTIONS`. A perpetual mirror
refresh must not burn tenant credits — B13's whole point — and it is admitted
at the platform budget exactly as the record sweep is.

**Transport injected, no live call** — the Inc-4/Inc-5 precedent. `DriveSource`
is a Protocol; the live SharePoint/Google adapters are activation-time ops.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.library.provenance import SourceKind, content_hash

logger = logging.getLogger(__name__)

__all__ = ["DriveFile", "DriveSource", "sync_drive"]


@dataclass(frozen=True)
class DriveFile:
    """One file as the drive describes it."""

    external_id: str
    name: str
    #: Extracted text. None means the adapter could not read it — the document
    #: is still filed (the provenance is real), it is simply not chunked.
    body: Optional[str] = None
    uri: Optional[str] = None
    mime_type: Optional[str] = None
    #: The source system's own hash, when it has one. Where it is absent we
    #: compute ours from the extracted text, which is why unchanged files can
    #: still be skipped without a fetch on the *next* pass.
    etag: Optional[str] = None


@runtime_checkable
class DriveSource(Protocol):
    """The connector-specific file feed. Injected — never a live call here."""

    async def list_files(self, scope: str) -> Sequence[DriveFile]:
        ...


def _hash_for(file: DriveFile) -> Optional[str]:
    if file.etag:
        return file.etag
    if file.body:
        return content_hash(file.body)
    return None


async def sync_drive(
    db: AsyncSession, company_id: uuid.UUID, connector_id: str,
    source: DriveSource, *, scope: str = "", memory_domain: Optional[str] = None,
    redis: Any = None,
) -> dict[str, Any]:
    """Mirror one bound drive scope into `documents`. Returns a tally.

    The four outcomes per file — created, updated, skipped, superseded — are
    counted separately because "the sync ran" and "the sync did anything" are
    different facts, and a mirror that silently skips everything looks
    identical to one that is working.
    """
    from src.ai.orm.document import Document

    files = list(await source.list_files(scope))
    seen: set[str] = set()
    tally = {"created": 0, "updated": 0, "skipped": 0, "superseded": 0}

    existing = {
        row["external_ref"]: row
        for row in (await db.execute(text("""
            SELECT id, external_ref, content_hash, staleness_state
            FROM documents
            WHERE company_id = CAST(:company_id AS uuid)
              AND source_kind = :kind
              AND external_ref IS NOT NULL
              AND superseded_by_id IS NULL
        """), {"company_id": str(company_id),
               "kind": SourceKind.CONNECTED_DRIVE})).mappings().all()
    }

    for file in files:
        seen.add(file.external_id)
        digest = _hash_for(file)
        prior = existing.get(file.external_id)
        # A file that vanished and came back. Its content is unchanged, so the
        # hash comparison below would skip it and leave it flagged `superseded`
        # *forever* — present in the drive, invisible in the Library, and with
        # nothing anywhere reporting the inconsistency. Found by the test that
        # removed a file and put it back.
        #
        # Revived rather than re-created: the document keeps its id, and with
        # it every `retrieval_usages` row and every rolled-up day of influence
        # history that points at it. A duplicate would orphan all of that.
        revived = prior is not None and prior["staleness_state"] == "superseded"

        if (prior is not None and not revived
                and digest is not None and prior["content_hash"] == digest):
            # Unchanged. Step 2 of §8: skipped *without a fetch* — which is why
            # the adapter is allowed to return a DriveFile with no body when it
            # already knows the etag.
            tally["skipped"] += 1
            continue

        document_id: Any
        if prior is None:
            document = Document(
                id=uuid.uuid4(), company_id=company_id,
                filename=file.name,
                file_type=(file.name.rsplit(".", 1)[-1] if "." in file.name else "bin").lower(),
                upload_status="completed", memory_domain=memory_domain,
                source_kind=SourceKind.CONNECTED_DRIVE,
                source_uri=file.uri, external_ref=file.external_id,
                content_hash=digest,
            )
            db.add(document)
            await db.flush()
            document_id = document.id
            tally["created"] += 1
        else:
            document_id = prior["id"]
            await db.execute(text("""
                UPDATE documents
                SET filename = :name, source_uri = :uri, content_hash = :digest,
                    staleness_state = 'fresh', staleness_reason = :reason
                WHERE id = :document_id
            """), {"name": file.name, "uri": file.uri, "digest": digest,
                   "reason": ("returned to the connected drive" if revived
                              else "refreshed from the connected drive"),
                   "document_id": document_id})
            tally["updated"] += 1

        if file.body and file.body.strip():
            await _rechunk_document(db, company_id, document_id, file)

    # Files that vanished from the source. Marked, never deleted (decision 3).
    # `superseded_by_id` stays NULL — nothing replaced it, it simply left — so
    # the state is carried by `staleness_state` and its reason instead.
    for external_ref, row in existing.items():
        if external_ref in seen:
            continue
        await db.execute(text("""
            UPDATE documents
            SET staleness_state = 'superseded',
                staleness_reason = 'no longer present in the connected drive'
            WHERE id = :document_id
        """), {"document_id": row["id"]})
        tally["superseded"] += 1

    await _emit_document_synced(company_id, connector_id, tally, redis)
    return {**tally, "files": len(files), "connector": connector_id}


async def _rechunk_document(
    db: AsyncSession, company_id: uuid.UUID, document_id: Any, file: DriveFile,
) -> None:
    """Replace a mirrored document's chunks from its new body.

    Delete-then-insert rather than diff: a drive file is mirrored wholesale, so
    a partial chunk update would leave the document describing two versions of
    itself at once.
    """
    from src.ai.memory.chunking import CURRENT_CHUNK_VERSION, chunk_document
    from src.ai.memory.embedding_service import EmbeddingService
    from src.ai.orm.document import DocumentChunk

    pieces = chunk_document(file.body or "", source_type=file.mime_type)
    if not pieces:
        return

    embedder = EmbeddingService(db, company_id)
    await db.execute(
        text("DELETE FROM document_chunks WHERE document_id = CAST(:d AS uuid)"),
        {"d": str(document_id)})
    for piece in pieces:
        embedding = None
        try:
            embedding = await embedder.embed_text(
                piece.content, task_type="RETRIEVAL_DOCUMENT")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Embedding failed during drive sync of %s: %s",
                         document_id, exc)
        db.add(DocumentChunk(
            document_id=document_id, chunk_index=str(piece.index),
            content=piece.content, embedding=embedding,
            heading_path=piece.heading_label or None,
            chunk_version=CURRENT_CHUNK_VERSION,
        ))
    await db.flush()


async def _emit_document_synced(
    company_id: uuid.UUID, connector_id: str, tally: dict[str, int], redis: Any,
) -> Optional[uuid.UUID]:
    """Announce the mirror pass on the bus, in its own transaction.

    Separate session for the reason HANDOFF §5 records: documents are
    control-plane here but the emit still gets its own transaction, so a signal
    failure never rolls back a completed mirror.
    """
    from src.ai.signals.models import SignalSource, SignalTrust, SignalTypes
    from src.ai.signals.service import emit_signal
    from src.common.database import AsyncSessionLocal

    if not any(tally[key] for key in ("created", "updated", "superseded")):
        # Nothing moved. A signal per idle poll would drown the bus in
        # "nothing happened", which is the fastest way to make a channel
        # unreadable.
        return None
    try:
        async with AsyncSessionLocal() as cp:
            sig_id = await emit_signal(
                cp, company_id=company_id, source=SignalSource.CONNECTOR,
                type=SignalTypes.DOCUMENT_SYNCED, trust=SignalTrust.INTERNAL,
                payload={"connector": connector_id, **tally},
            )
            await cp.commit()
            return sig_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("document.synced emit failed for %s: %s", connector_id, exc)
        return None
