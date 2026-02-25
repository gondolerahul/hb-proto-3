"""
Asset Router — REST API for asset management (list, upload, download, delete).
"""
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.database import get_db
from src.auth.router import get_current_user
from src.auth.models import User
from src.ai.asset_service import AssetService

router = APIRouter(prefix="/api/v1/assets", tags=["Assets"])


# ─── Response schemas ──────────────────────────────────────────────────────────

class AssetResponse(BaseModel):
    id: str
    company_id: str
    campaign_id: Optional[str]
    agent_id: Optional[str]
    run_id: Optional[str]
    file_type: str
    file_name: str
    file_path: str
    file_size: Optional[int]
    mime_type: Optional[str]
    duration_seconds: Optional[int]
    asset_metadata: Optional[dict]
    created_at: datetime
    download_url: str

    class Config:
        from_attributes = True


def _to_response(asset, request_base_url: str = "") -> dict:
    return {
        "id": str(asset.id),
        "company_id": str(asset.company_id),
        "campaign_id": str(asset.campaign_id) if asset.campaign_id else None,
        "agent_id": str(asset.agent_id) if asset.agent_id else None,
        "run_id": str(asset.run_id) if asset.run_id else None,
        "file_type": asset.file_type,
        "file_name": asset.file_name,
        "file_path": asset.file_path,
        "file_size": asset.file_size,
        "mime_type": asset.mime_type,
        "duration_seconds": asset.duration_seconds,
        "asset_metadata": asset.asset_metadata,
        "created_at": asset.created_at.isoformat(),
        "download_url": f"/api/v1/assets/{asset.id}/download",
    }


# ─── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", summary="List assets with optional filters")
async def list_assets(
    file_type: Optional[str] = Query(None, description="recordings | images | videos"),
    agent_id: Optional[UUID] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = AssetService(db)
    assets = await svc.list_assets(
        company_id=current_user.company_id,
        file_type=file_type,
        agent_id=agent_id,
        campaign_id=campaign_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"assets": [_to_response(a) for a in assets], "count": len(assets)}


@router.post("/upload", summary="Upload a new asset file")
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = Form(..., description="recordings | images | videos"),
    campaign_id: Optional[UUID] = Form(None),
    agent_id: Optional[UUID] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if asset_type not in ("recordings", "images", "videos"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="asset_type must be one of: recordings, images, videos",
        )

    svc = AssetService(db)
    asset = await svc.save_upload(
        upload=file,
        asset_type=asset_type,
        company_id=current_user.company_id,
        campaign_id=campaign_id,
        agent_id=agent_id,
    )
    return _to_response(asset)


@router.get("/{asset_id}", summary="Get single asset metadata")
async def get_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = AssetService(db)
    asset = await svc.get_asset(asset_id, current_user.company_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return _to_response(asset)


@router.get("/{asset_id}/download", summary="Download/stream asset file")
async def download_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = AssetService(db)
    asset = await svc.get_asset(asset_id, current_user.company_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    file_path = Path(asset.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset file not found on disk")

    media_type = asset.mime_type or mimetypes.guess_type(asset.file_name)[0] or "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        filename=asset.file_name,
        media_type=media_type,
    )


@router.delete("/{asset_id}", summary="Delete an asset")
async def delete_asset(
    asset_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = AssetService(db)
    deleted = await svc.delete_asset(asset_id, current_user.company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"message": "Asset deleted successfully"}
