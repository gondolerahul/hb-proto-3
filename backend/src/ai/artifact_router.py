"""
Artifact Router — REST API for artifact management (list, upload, download, delete).
All routes are at /api/v1/artifacts.
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
from src.ai.artifact_service import ArtifactService, ORIGIN_USER, ORIGIN_SYSTEM

router = APIRouter(prefix="/api/v1/artifacts", tags=["Artifacts"])


# ─── Response schemas ──────────────────────────────────────────────────────────

class ArtifactResponse(BaseModel):
    id: str
    company_id: str
    campaign_id: Optional[str]
    agent_id: Optional[str]
    run_id: Optional[str]
    origin: str
    file_category: str
    file_name: str
    file_path: str
    file_size: Optional[int]
    mime_type: Optional[str]
    duration_seconds: Optional[int]
    purpose: Optional[str]
    generated_by: Optional[str]
    artifact_metadata: Optional[dict]
    created_at: datetime
    download_url: str

    class Config:
        from_attributes = True


def _to_response(artifact) -> dict:
    return {
        "id": str(artifact.id),
        "company_id": str(artifact.company_id),
        "campaign_id": str(artifact.campaign_id) if artifact.campaign_id else None,
        "agent_id": str(artifact.agent_id) if artifact.agent_id else None,
        "run_id": str(artifact.run_id) if artifact.run_id else None,
        "origin": artifact.origin,
        "file_category": artifact.file_category,
        "file_name": artifact.file_name,
        "file_path": artifact.file_path,
        "file_size": artifact.file_size,
        "mime_type": artifact.mime_type,
        "duration_seconds": artifact.duration_seconds,
        "purpose": artifact.purpose,
        "generated_by": artifact.generated_by,
        "artifact_metadata": artifact.artifact_metadata,
        "created_at": artifact.created_at.isoformat(),
        "download_url": f"/api/v1/artifacts/{artifact.id}/download",
    }


# ─── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", summary="List artifacts with optional filters")
async def list_artifacts(
    origin: Optional[str] = Query(None, description="user-uploads | system-generated"),
    file_category: Optional[str] = Query(None, description="recordings | images | videos | documents | text"),
    agent_id: Optional[UUID] = Query(None),
    campaign_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ArtifactService(db)
    artifacts = await svc.list_artifacts(
        company_id=current_user.company_id,
        origin=origin,
        file_category=file_category,
        agent_id=agent_id,
        campaign_id=campaign_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"artifacts": [_to_response(a) for a in artifacts], "count": len(artifacts)}


@router.post("/upload", summary="Upload a new artifact file")
async def upload_artifact(
    file: UploadFile = File(...),
    file_category: str = Form(..., description="recordings | images | videos | documents | text"),
    campaign_id: Optional[UUID] = Form(None),
    agent_id: Optional[UUID] = Form(None),
    purpose: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid_categories = ("recordings", "images", "videos", "documents", "text")
    if file_category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"file_category must be one of: {', '.join(valid_categories)}",
        )

    svc = ArtifactService(db)
    artifact = await svc.save_upload(
        upload=file,
        file_category=file_category,
        company_id=current_user.company_id,
        campaign_id=campaign_id,
        agent_id=agent_id,
        purpose=purpose,
    )
    return _to_response(artifact)


@router.get("/{artifact_id}", summary="Get single artifact metadata")
async def get_artifact(
    artifact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ArtifactService(db)
    artifact = await svc.get_artifact(artifact_id, current_user.company_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _to_response(artifact)


@router.get("/{artifact_id}/download", summary="Download/stream artifact file")
async def download_artifact(
    artifact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ArtifactService(db)
    artifact = await svc.get_artifact(artifact_id, current_user.company_id)
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    file_path = Path(artifact.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found on disk")

    media_type = artifact.mime_type or mimetypes.guess_type(artifact.file_name)[0] or "application/octet-stream"
    return FileResponse(
        path=str(file_path),
        filename=artifact.file_name,
        media_type=media_type,
    )


@router.delete("/{artifact_id}", summary="Delete an artifact")
async def delete_artifact(
    artifact_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = ArtifactService(db)
    deleted = await svc.delete_artifact(artifact_id, current_user.company_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return {"message": "Artifact deleted successfully"}
