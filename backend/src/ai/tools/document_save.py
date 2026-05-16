"""
DocumentSaveTool — Save sandbox-generated documents to the artifact system.

Used by Document Renderer and Revision Agent after sandbox_code creates
a document file. Copies from sandbox temp dir to artifact storage and
registers the file in the Artifact DB.
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.ai.tools.base import Tool

# Artifact root for system-generated files
BASE_DIR = Path(__file__).resolve().parents[3] / "artifact" / "system-generated"

# MIME type mapping for document formats
_MIME_TYPES: Dict[str, str] = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "png": "image/png",
    "svg": "image/svg+xml",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


class DocumentSaveTool(Tool):
    """Save a generated document file to the platform artifact system.

    Copies a file from the sandbox temp directory to persistent artifact
    storage and registers it in the Artifact DB for traceability.

    Actions:
        save — Copy file from source_path to artifact storage and register
    """

    name = "document_save"
    description = (
        "Save a generated document file to the artifact system. "
        "Input: JSON with 'source_path' (path to file in sandbox), "
        "'filename' (display name), 'format' (pptx/docx/xlsx/pdf), "
        "and optional 'purpose' description. "
        "Returns JSON with artifact_id, file_path, and file_size."
    )

    async def run(self, input_data: str) -> str:
        return await self.run_with_context(input_data, context=None)

    async def run_with_context(self, input_data: str, context=None) -> str:
        try:
            params = json.loads(input_data) if isinstance(input_data, str) else input_data
        except (json.JSONDecodeError, TypeError):
            return json.dumps({"error": "Invalid JSON input. Expected: {source_path, filename, format}"})

        source_path = params.get("source_path", "")
        filename = params.get("filename", "")
        doc_format = params.get("format", "").lower()
        purpose = params.get("purpose", "AI-generated document")

        # Validate required fields
        if not source_path:
            return json.dumps({"error": "Missing 'source_path'"})
        if not filename:
            return json.dumps({"error": "Missing 'filename'"})
        if not doc_format:
            return json.dumps({"error": "Missing 'format' (pptx/docx/xlsx/pdf)"})

        # Validate source file exists
        if not os.path.exists(source_path):
            return json.dumps({"error": f"Source file not found: {source_path}"})

        # Resolve MIME type
        mime_type = _MIME_TYPES.get(doc_format)
        if not mime_type:
            return json.dumps({
                "error": f"Unknown format '{doc_format}'. Supported: {', '.join(_MIME_TYPES.keys())}"
            })

        # Ensure filename has correct extension
        expected_ext = f".{doc_format}"
        if not filename.lower().endswith(expected_ext):
            filename = f"{filename}{expected_ext}"

        # Resolve company_id from context
        company_id = (context or {}).get("company_id", params.get("company_id", "default"))

        # Build output directory
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        output_dir = BASE_DIR / str(company_id) / date_str
        output_dir.mkdir(parents=True, exist_ok=True)

        # Copy file to artifact storage
        dest_path = output_dir / filename
        try:
            shutil.copy2(source_path, str(dest_path))
        except Exception as e:
            return json.dumps({"error": f"Failed to copy file: {str(e)}"})

        file_size = dest_path.stat().st_size

        # Register in artifact DB
        artifact_id = await self._register_artifact(
            file_path=dest_path,
            filename=filename,
            mime_type=mime_type,
            company_id=company_id,
            purpose=purpose,
            doc_format=doc_format,
        )

        return json.dumps({
            "status": "success",
            "artifact_id": artifact_id,
            "file_path": str(dest_path),
            "filename": filename,
            "format": doc_format,
            "file_size": file_size,
            "mime_type": mime_type,
            "message": f"Saved {filename} ({file_size:,} bytes) to artifact storage",
        })

    @staticmethod
    async def _register_artifact(
        file_path: Path,
        filename: str,
        mime_type: str,
        company_id: str,
        purpose: str,
        doc_format: str,
    ) -> Optional[str]:
        """Register the document in the Artifact DB. Returns artifact ID or None."""
        if not company_id or company_id == "default":
            return None
        try:
            from uuid import UUID as _UUID
            from src.common.database import AsyncSessionLocal
            from src.ai.artifact_service import ArtifactService, ORIGIN_SYSTEM

            async with AsyncSessionLocal() as _db:
                art_svc = ArtifactService(_db)
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
                artifact = await art_svc.save_artifact(
                    file_bytes=file_bytes,
                    file_name=filename,
                    mime_type=mime_type,
                    file_category="documents",
                    origin=ORIGIN_SYSTEM,
                    company_id=_UUID(str(company_id)),
                    purpose=purpose,
                    generated_by="document_save",
                    extra_metadata={"format": doc_format},
                )
                return str(artifact.id) if artifact else None
        except Exception:
            return None  # Non-fatal — file is already saved to disk

    def get_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "source_path": {
                        "type": "string",
                        "description": "Absolute path to the generated file in sandbox (e.g. /tmp/sandbox/<id>/report.pptx)",
                    },
                    "filename": {
                        "type": "string",
                        "description": "Display filename for the artifact (e.g. 'investor_pitch_deck.pptx')",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["pptx", "docx", "xlsx", "pdf", "png", "svg"],
                        "description": "Document format",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Optional description of the document's purpose",
                    },
                },
                "required": ["source_path", "filename", "format"],
            },
        }
