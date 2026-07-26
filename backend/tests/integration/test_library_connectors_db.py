"""Inc 6 / LIB T7–T8 — connected drives and credential expiry. ``needs_db``.

Transport injected throughout, no live call — the Inc-4/Inc-5 precedent. What
these tests actually pin is the *policy*, which is where the interesting
decisions are:

* a file that vanished from the source is marked, **never deleted** (decision
  3) — a drive misconfiguration must not destroy a tenant's Library;
* an unchanged file is skipped **without a fetch**, which is why the adapter is
  allowed to return a `DriveFile` carrying an etag and no body;
* a NULL `credentials_expire_at` is **not** a warning — most API keys have no
  expiry, and warning about them daily would train every tenant to ignore the
  one signal that matters.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from src.ai.connectors.credential_expiry import (
    expiring_bindings,
    sweep_expiring_credentials,
)
from src.ai.connectors.document_sync import DriveFile, sync_drive
from src.ai.library.provenance import SourceKind

pytestmark = [pytest.mark.needs_db, pytest.mark.asyncio]

NOW = datetime(2026, 7, 26, 3, 0, 0)


class FakeDrive:
    """The injected transport. `list_files` is the whole surface."""

    def __init__(self, files):
        self._files = list(files)
        self.calls = 0

    async def list_files(self, scope):
        self.calls += 1
        return list(self._files)


@pytest_asyncio.fixture
async def connector_fixture():
    import os

    from src.common.config import settings
    if not (getattr(settings, "DATABASE_URL", None) or os.environ.get("DATABASE_URL")):
        pytest.skip("DATABASE_URL not set")
    from src.common.database import AsyncSessionLocal, engine

    await engine.dispose()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO companies (id, name, type, status, created_at, updated_at) "
                 "VALUES (:id, :n, 'TENANT', 'active', now(), now())"),
            {"id": str(cid), "n": f"lib-conn-{cid.hex[:8]}"})
        await s.commit()
    try:
        yield {"company": cid}
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM signals WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM connector_bindings WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text(
                "DELETE FROM document_chunks WHERE document_id IN "
                "(SELECT id FROM documents WHERE company_id = :c)"), {"c": str(cid)})
            await s.execute(text("DELETE FROM documents WHERE company_id = :c"),
                            {"c": str(cid)})
            await s.execute(text("DELETE FROM companies WHERE id = :c"), {"c": str(cid)})
            await s.commit()


class TestCatalog:
    def test_both_drives_are_cataloged_and_master_nothing(self):
        """A drive is a source of documents, not of records — so it declares
        no masters and the Inc-4 mastering machine never engages."""
        from src.ai.connectors.catalog import CONNECTOR_CATALOG

        by_id = {c.connector_id: c for c in CONNECTOR_CATALOG}
        for connector_id in ("sharepoint_drive", "google_drive"):
            assert connector_id in by_id, connector_id
            assert by_id[connector_id].domain == "knowledge"
            assert by_id[connector_id].masters == ()


class TestDriveSync:
    async def test_new_files_become_documents(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        drive = FakeDrive([
            DriveFile("f1", "handbook.md", body="the staff handbook", uri="/drive/f1"),
            DriveFile("f2", "prices.md", body="our price list", uri="/drive/f2"),
        ])
        async with AsyncSessionLocal() as s:
            tally = await sync_drive(s, f["company"], "google_drive", drive)
            await s.commit()
            rows = (await s.execute(text(
                "SELECT external_ref, source_kind, source_uri, content_hash "
                "FROM documents WHERE company_id = :c ORDER BY external_ref"),
                {"c": str(f["company"])})).mappings().all()

        assert tally["created"] == 2
        assert [r["external_ref"] for r in rows] == ["f1", "f2"]
        assert all(r["source_kind"] == SourceKind.CONNECTED_DRIVE for r in rows)
        assert all(r["content_hash"] for r in rows), "computed where the etag is absent"

    async def test_an_unchanged_file_is_skipped(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        files = [DriveFile("f1", "handbook.md", body="the staff handbook")]
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive(files))
            await s.commit()
            second = await sync_drive(s, f["company"], "google_drive", FakeDrive(files))
            await s.commit()

        assert second["skipped"] == 1
        assert second["created"] == 0
        assert second["updated"] == 0

    async def test_an_etag_lets_the_adapter_skip_without_a_body(self, connector_fixture):
        """Step 2 of §8: compare the hash, skip without a fetch. The adapter
        returning no body on the second pass is the point of the design."""
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "sharepoint_drive", FakeDrive([
                DriveFile("f1", "h.md", body="content", etag="v1")]))
            await s.commit()
            second = await sync_drive(s, f["company"], "sharepoint_drive", FakeDrive([
                DriveFile("f1", "h.md", body=None, etag="v1")]))
            await s.commit()

        assert second["skipped"] == 1

    async def test_a_changed_file_updates_and_refreshes_staleness(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "prices.md", body="old prices", etag="v1")]))
            await s.commit()
            # Mark it stale, as the T4 sweep would.
            await s.execute(text(
                "UPDATE documents SET staleness_state = 'stale' WHERE company_id = :c"),
                {"c": str(f["company"])})
            await s.commit()

            tally = await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "prices.md", body="new prices", etag="v2")]))
            await s.commit()
            row = (await s.execute(text(
                "SELECT staleness_state, content_hash FROM documents WHERE company_id = :c"),
                {"c": str(f["company"])})).mappings().one()

        assert tally["updated"] == 1
        assert row["staleness_state"] == "fresh"
        assert row["content_hash"] == "v2"

    async def test_a_vanished_file_is_superseded_never_deleted(self, connector_fixture):
        """Decision 3. A drive misconfiguration that briefly hides a folder
        must not silently destroy a tenant's Library."""
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "a.md", body="a"),
                DriveFile("f2", "b.md", body="b")]))
            await s.commit()

            tally = await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "a.md", body="a")]))
            await s.commit()

            rows = {r["external_ref"]: r for r in (await s.execute(text(
                "SELECT external_ref, staleness_state, staleness_reason "
                "FROM documents WHERE company_id = :c"),
                {"c": str(f["company"])})).mappings().all()}

        assert tally["superseded"] == 1
        assert len(rows) == 2, "the vanished file's document must still exist"
        assert rows["f2"]["staleness_state"] == "superseded"
        assert "no longer present" in rows["f2"]["staleness_reason"]

    async def test_a_returning_file_is_revived_not_left_superseded(
            self, connector_fixture):
        """**The defect this test found.** A file that vanishes and comes back
        has unchanged content, so the hash comparison skipped it and left it
        flagged `superseded` forever — present in the drive, invisible in the
        Library, with nothing anywhere reporting the inconsistency.

        Revived in place rather than re-created, so the document keeps its id
        and with it every usage row and rolled-up day of influence pointing at
        it. A duplicate would have orphaned all of that.
        """
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "a.md", body="a")]))
            await s.commit()
            original_id = (await s.execute(text(
                "SELECT id FROM documents WHERE company_id = :c"),
                {"c": str(f["company"])})).scalar()

            await sync_drive(s, f["company"], "google_drive", FakeDrive([]))
            await s.commit()

            tally = await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "a.md", body="a")]))
            await s.commit()

            rows = (await s.execute(text(
                "SELECT id, staleness_state, staleness_reason FROM documents "
                "WHERE company_id = :c"), {"c": str(f["company"])})).mappings().all()

        assert tally["updated"] == 1
        assert len(rows) == 1, "revived in place, not duplicated"
        assert rows[0]["id"] == original_id, "the influence history must survive"
        assert rows[0]["staleness_state"] == "fresh"
        assert "returned to" in rows[0]["staleness_reason"]

    async def test_an_idle_pass_emits_no_signal(self, connector_fixture):
        """A signal per idle poll would drown the bus in 'nothing happened',
        which is the fastest way to make a channel unreadable."""
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive([]))
            await s.commit()
            count = (await s.execute(text(
                "SELECT COUNT(*) FROM signals WHERE company_id = :c "
                "AND type = 'document.synced'"), {"c": str(f["company"])})).scalar()
        assert count == 0

    async def test_a_productive_pass_emits_document_synced(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await sync_drive(s, f["company"], "google_drive", FakeDrive([
                DriveFile("f1", "a.md", body="a")]))
            await s.commit()

        async with AsyncSessionLocal() as s:
            row = (await s.execute(text(
                "SELECT type, payload FROM signals WHERE company_id = :c "
                "AND type = 'document.synced'"), {"c": str(f["company"])})).mappings().first()
        assert row is not None
        assert row["payload"]["created"] == 1


class TestCredentialExpiry:
    async def _bind(self, s, company, connector_id, expires_at):
        await s.execute(text("""
            INSERT INTO connector_bindings
                (id, company_id, connector_id, tool_allow, write_allow, status,
                 credentials_expire_at, created_at, updated_at)
            VALUES (:id, :c, :ci, '[]', '[]', 'active', :exp, now(), now())
        """), {"id": str(uuid.uuid4()), "c": str(company), "ci": connector_id,
               "exp": expires_at})

    async def test_a_null_expiry_is_not_a_warning(self, connector_fixture):
        """Most API keys have no expiry. Warning about them daily would train
        every tenant to ignore this signal."""
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await self._bind(s, f["company"], "zoho_books", None)
            await s.commit()
            at_risk = await expiring_bindings(s, warn_days=14, now=NOW)
        assert at_risk == []

    async def test_an_expiry_inside_the_window_is_found(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await self._bind(s, f["company"], "google_drive", NOW + timedelta(days=5))
            await s.commit()
            at_risk = await expiring_bindings(s, warn_days=14, now=NOW)

        assert len(at_risk) == 1
        assert at_risk[0]["connector_id"] == "google_drive"
        assert at_risk[0]["days_remaining"] == 5
        assert at_risk[0]["already_expired"] is False

    async def test_an_expiry_beyond_the_window_is_not(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await self._bind(s, f["company"], "google_drive", NOW + timedelta(days=90))
            await s.commit()
            at_risk = await expiring_bindings(s, warn_days=14, now=NOW)
        assert at_risk == []

    async def test_an_already_expired_binding_is_flagged_as_such(self, connector_fixture):
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await self._bind(s, f["company"], "sharepoint_drive", NOW - timedelta(days=2))
            await s.commit()
            at_risk = await expiring_bindings(s, warn_days=14, now=NOW)

        assert at_risk[0]["already_expired"] is True
        assert at_risk[0]["days_remaining"] < 0

    async def test_the_sweep_emits_once_per_binding_per_day(self, connector_fixture):
        """Deduped on binding *and* day, so a restarted worker does not
        re-announce everything it announced this morning."""
        from src.common.database import AsyncSessionLocal

        f = connector_fixture
        async with AsyncSessionLocal() as s:
            await self._bind(s, f["company"], "google_drive", NOW + timedelta(days=3))
            await s.commit()

            first = await sweep_expiring_credentials(s, warn_days=14, now=NOW)
            await s.commit()
            second = await sweep_expiring_credentials(s, warn_days=14, now=NOW)
            await s.commit()

            count = (await s.execute(text(
                "SELECT COUNT(*) FROM signals WHERE company_id = :c "
                "AND type = 'connector.credentials_expiring'"),
                {"c": str(f["company"])})).scalar()

        assert first["emitted"] == 1
        assert count == 1, f"second sweep emitted a duplicate: {second}"
