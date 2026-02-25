"""
Asset Service — manages file storage and metadata for all system-generated assets.
Storage path convention: assets/{tenant_id}/{campaign_id}/{asset_type}/{YYYY-MM-DD}/{file_name}
"""
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.ai.asset_models import Asset

# Base directory for all assets (relative to backend runtime dir)
ASSETS_BASE_DIR = Path("assets")


def get_storage_path(
    tenant_id: UUID,
    asset_type: str,
    campaign_id: Optional[UUID] = None,
) -> Path:
    """
    Build the hierarchical storage path for an asset.
    Format: assets/{tenant_id}/{campaign_id}/{asset_type}/{YYYY-MM-DD}/
    If campaign_id is None, uses 'default' as the campaign folder.
    """
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    campaign_str = str(campaign_id) if campaign_id else "default"
    return ASSETS_BASE_DIR / str(tenant_id) / campaign_str / asset_type / date_str


class AssetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_asset(
        self,
        file_bytes: bytes,
        file_name: str,
        mime_type: str,
        asset_type: str,             # recordings | images | videos
        company_id: UUID,
        campaign_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
        duration_seconds: Optional[int] = None,
        extra_metadata: Optional[dict] = None,
    ) -> Asset:
        """
        Write file to disk and create DB record.
        Returns the created Asset ORM object.
        """
        # Build storage path
        storage_dir = get_storage_path(company_id, asset_type, campaign_id)
        storage_dir.mkdir(parents=True, exist_ok=True)

        # Ensure unique filename
        unique_name = f"{uuid.uuid4().hex}_{file_name}"
        file_path = storage_dir / unique_name

        # Write to disk
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Create DB record
        asset = Asset(
            company_id=company_id,
            campaign_id=campaign_id,
            agent_id=agent_id,
            run_id=run_id,
            file_type=asset_type,
            file_name=file_name,
            file_path=str(file_path),
            file_size=len(file_bytes),
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            asset_metadata=extra_metadata or {},
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def save_upload(
        self,
        upload: UploadFile,
        asset_type: str,
        company_id: UUID,
        campaign_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
    ) -> Asset:
        """Convenience method to save a FastAPI UploadFile directly."""
        content = await upload.read()
        return await self.save_asset(
            file_bytes=content,
            file_name=upload.filename or "upload",
            mime_type=upload.content_type or "application/octet-stream",
            asset_type=asset_type,
            company_id=company_id,
            campaign_id=campaign_id,
            agent_id=agent_id,
        )

    async def list_assets(
        self,
        company_id: UUID,
        file_type: Optional[str] = None,
        agent_id: Optional[UUID] = None,
        campaign_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Asset]:
        """Return filtered asset list for a company."""
        conditions = [Asset.company_id == company_id]

        if file_type:
            conditions.append(Asset.file_type == file_type)
        if agent_id:
            conditions.append(Asset.agent_id == agent_id)
        if campaign_id:
            conditions.append(Asset.campaign_id == campaign_id)
        if date_from:
            conditions.append(Asset.created_at >= date_from)
        if date_to:
            conditions.append(Asset.created_at <= date_to)

        stmt = (
            select(Asset)
            .where(and_(*conditions))
            .order_by(Asset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_asset(self, asset_id: UUID, company_id: UUID) -> Optional[Asset]:
        """Fetch a single asset by ID, scoped to company."""
        stmt = select(Asset).where(
            Asset.id == asset_id,
            Asset.company_id == company_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_asset(self, asset_id: UUID, company_id: UUID) -> bool:
        """Delete asset record and its physical file."""
        asset = await self.get_asset(asset_id, company_id)
        if not asset:
            return False
        # Remove file from disk
        try:
            Path(asset.file_path).unlink(missing_ok=True)
        except Exception:
            pass
        await self.db.delete(asset)
        await self.db.commit()
        return True
