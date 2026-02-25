"""
Image Generation Tool using Google Gemini API.

Supports:
- Text-to-image generation
- Image editing with reference images
- API key resolution from IntegrationRegistry (primary) with env-var fallback
- Cost logging via IntegrationRegistry SKU
"""
import logging
import json
import base64
import os
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)

# Try to import Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google.genai SDK not available for image generation")


class ImageGenerationTool(Tool):
    """
    AI tool for generating images using Google Gemini image generation models.
    
    API key resolution order (per request):
      1. IntegrationRegistry DB lookup using company_id from execution context
         (looks up by model_name SKU, then by service_category='IMAGE_GENERATION',
          then by provider='google')
      2. GOOGLE_API_KEY env var
      3. GEMINI_API_KEY env var
    
    Accepts a model name, prompt, and optional reference image to generate images.
    """
    name = "image_generation"
    description = (
        "Generate images from text prompts using AI models. "
        "Can also edit existing images by providing a reference image. "
        "Input should be a JSON string with: "
        "'model_name' (e.g. 'gemini-3-pro-image-preview'), "
        "'prompt' (text description of desired image), "
        "and optionally 'reference_image_path' (path to an existing image for editing)."
    )

    # Output directory for generated images — saved under backend/artifact
    BASE_ARTIFACT_DIR = Path(__file__).resolve().parents[3] / "artifact"
    # Fallback legacy dir
    OUTPUT_DIR = str(BASE_ARTIFACT_DIR / "generated_images")

    def get_function_schema(self) -> Dict[str, Any]:
        """Return JSON schema for Gemini function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "The image generation model to use (e.g. 'gemini-3-pro-image-preview')"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Text description of the image to generate"
                    },
                    "reference_image_path": {
                        "type": "string",
                        "description": "Optional path to a reference image for image editing/modification"
                    }
                },
                "required": ["model_name", "prompt"]
            }
        }

    async def _resolve_api_key(self, model_name: str, company_id: Optional[str] = None) -> Optional[str]:
        """Resolve the Gemini API key from the integration registry or environment.

        Resolution order:
          1. DB – exact model_name match in integration_registry
          2. DB – any IMAGE_GENERATION entry for the company (any provider)
          3. DB – any 'google' or 'gemini' provider entry (case-insensitive)
          4. GOOGLE_API_KEY env var
          5. GEMINI_API_KEY env var

        Args:
            model_name: The image generation model name being requested
            company_id: Company UUID string from execution context, or None

        Returns:
            Decrypted API key string, or None if not found anywhere
        """
        if company_id:
            try:
                from uuid import UUID as _UUID
                from src.common.database import AsyncSessionLocal
                from sqlalchemy import select, func
                from src.config.models import IntegrationRegistry
                from src.common.security import decrypt_api_key

                async with AsyncSessionLocal() as db:
                    company_uuid = _UUID(str(company_id))

                    # Strategy 1: exact model name match
                    result = await db.execute(
                        select(IntegrationRegistry).where(
                            IntegrationRegistry.company_id == company_uuid,
                            IntegrationRegistry.model_name == model_name,
                            IntegrationRegistry.status == "active",
                            IntegrationRegistry.encrypted_api_key.isnot(None)
                        )
                    )
                    entry = result.scalars().first()
                    if entry and entry.encrypted_api_key:
                        logger.info(f"[ImageGen] API key resolved via model_name='{model_name}' for company {company_id}")
                        return decrypt_api_key(entry.encrypted_api_key)

                    # Strategy 2: any IMAGE_GENERATION category entry for this company
                    result = await db.execute(
                        select(IntegrationRegistry).where(
                            IntegrationRegistry.company_id == company_uuid,
                            IntegrationRegistry.service_category == "IMAGE_GENERATION",
                            IntegrationRegistry.status == "active",
                            IntegrationRegistry.encrypted_api_key.isnot(None)
                        )
                    )
                    entry = result.scalars().first()
                    if entry and entry.encrypted_api_key:
                        logger.info(f"[ImageGen] API key resolved via IMAGE_GENERATION category for company {company_id}")
                        return decrypt_api_key(entry.encrypted_api_key)

                    # Strategy 3: any 'google' or 'gemini' provider (case-insensitive)
                    result = await db.execute(
                        select(IntegrationRegistry).where(
                            IntegrationRegistry.company_id == company_uuid,
                            IntegrationRegistry.status == "active",
                            IntegrationRegistry.encrypted_api_key.isnot(None),
                            func.lower(IntegrationRegistry.provider_name).in_(["google", "gemini"])
                        )
                    )
                    entry = result.scalars().first()
                    if entry and entry.encrypted_api_key:
                        logger.info(f"[ImageGen] API key resolved via google/gemini provider for company {company_id}")
                        return decrypt_api_key(entry.encrypted_api_key)

            except Exception as e:
                logger.warning(f"[ImageGen] DB API key lookup failed (company={company_id}): {e}", exc_info=True)

        # Strategy 4 & 5: environment variables
        env_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if env_key:
            logger.info("[ImageGen] API key resolved from environment variable")
        return env_key

    def _get_output_dir(self, company_id: Optional[str] = None, user_id: Optional[str] = None) -> Path:
        """Resolve the output directory for saving generated images.
        
        Saves to backend/artifact/<company_id>/<user_id>/images/ when context
        is available; falls back to the legacy generated_images dir.
        """
        if company_id and user_id:
            out = self.BASE_ARTIFACT_DIR / str(company_id) / str(user_id) / "images"
        elif company_id:
            out = self.BASE_ARTIFACT_DIR / str(company_id) / "images"
        else:
            out = self.BASE_ARTIFACT_DIR / "generated_images"
        out.mkdir(parents=True, exist_ok=True)
        return out

    async def run(self, input_data: str) -> str:
        """Execute image generation without extra context (env-var API key only)."""
        return await self.run_with_context(input_data, context=None)

    async def run_with_context(self, input_data: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Execute image generation with execution context for DB key lookup.

        Args:
            input_data: JSON string with model_name, prompt, optional reference_image_path
            context: Execution context dict that may contain 'company_id' and 'user_id'

        Returns:
            JSON string with generation result including saved image path(s)
        """
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input. Expected: {\"model_name\": \"...\", \"prompt\": \"...\"}"})

        model_name = params.get("model_name", "gemini-3-pro-image-preview")
        prompt = params.get("prompt")
        reference_image_path = params.get("reference_image_path")

        # Pull company/user from context (injected by ToolExecutor)
        company_id = None
        user_id = None
        if context:
            company_id = context.get("company_id") or params.get("company_id")
            user_id = context.get("user_id") or params.get("user_id")

        if not prompt:
            return json.dumps({"error": "Missing required parameter: 'prompt'"})

        if not GENAI_AVAILABLE:
            return json.dumps({"error": "Google GenAI SDK not installed. Run: pip install google-genai"})

        # Resolve API key from DB or env
        api_key = await self._resolve_api_key(model_name, company_id)
        if not api_key:
            return json.dumps({
                "error": (
                    f"No API key found for image generation model '{model_name}'. "
                    f"Please configure a 'google' integration in the Integration Registry "
                    f"(service_category='IMAGE_GENERATION' or provider_name='google') "
                    f"for company {company_id}."
                )
            })

        try:
            client = genai.Client(api_key=api_key)

            # Build content parts
            contents = []

            # Add reference image if provided
            if reference_image_path and os.path.exists(reference_image_path):
                logger.info(f"Loading reference image from {reference_image_path}")
                with open(reference_image_path, "rb") as f:
                    image_bytes = f.read()

                ext = os.path.splitext(reference_image_path)[1].lower()
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                            ".webp": "image/webp", ".gif": "image/gif"}
                mime_type = mime_map.get(ext, "image/png")
                contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

            # Add text prompt
            contents.append(prompt)

            logger.info(f"[ImageGen] Generating with model={model_name}, company={company_id}, prompt='{prompt[:80]}...'")

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )

            # Determine output directory
            output_dir = self._get_output_dir(company_id, user_id)

            result = {
                "model": model_name,
                "prompt": prompt,
                "images": [],
                "text_response": None,
                "image_path": None,  # Convenience: path to the first generated image
            }

            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        result["text_response"] = part.text
                    elif hasattr(part, 'inline_data') and part.inline_data:
                        image_id = str(uuid.uuid4())[:8]
                        image_filename = f"panel_{image_id}.png"
                        image_path = str(output_dir / image_filename)

                        image_data = part.inline_data.data
                        if isinstance(image_data, str):
                            image_data = base64.b64decode(image_data)

                        with open(image_path, "wb") as f:
                            f.write(image_data)

                        result["images"].append({
                            "path": image_path,
                            "filename": image_filename,
                            "size_bytes": len(image_data)
                        })
                        if result["image_path"] is None:
                            result["image_path"] = image_path  # first image = convenience field

                        logger.info(f"[ImageGen] Image saved to {image_path}")

            if not result["images"]:
                logger.warning(f"[ImageGen] No image parts in response for model={model_name}. Response: {response}")
                return json.dumps({
                    "error": "No image was generated. The model may have filtered the request or returned text only.",
                    "text_response": result.get("text_response")
                })

            result["image_count"] = len(result["images"])
            return json.dumps(result)

        except Exception as e:
            logger.error(f"[ImageGen] Image generation error: {e}", exc_info=True)
            return json.dumps({"error": f"Image generation failed: {str(e)}"})
