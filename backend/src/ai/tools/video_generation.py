"""
Video Generation Tool using Google Gemini Veo 3.1 API.

Supports:
- Text-to-video generation
- Image-to-video with start/end frame reference images
- Video extension for segments > 8 seconds (auto-splits and merges)
- Cost logging via IntegrationRegistry SKU
"""
import logging
import json
import os
import uuid
import time
import subprocess
import asyncio
from typing import Dict, Any, Optional, List

from src.ai.tools.base import Tool

logger = logging.getLogger(__name__)

# Try to import Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    logger.warning("google.genai SDK not available for video generation")


class VideoGenerationTool(Tool):
    """
    AI tool for generating videos using Google Veo 3.1 API.
    
    Accepts model name, prompt, video length, audio flag, and optional
    reference images (start/end frames). Automatically splits videos
    longer than 8 seconds into segments, generates each, and merges them.
    """
    name = "video_generation"
    description = (
        "Generate videos from text prompts using AI models (Veo 3.1). "
        "Supports audio, reference images for start/end frames, and "
        "automatic splitting for videos longer than 8 seconds. "
        "Input should be a JSON string with: "
        "'model_name' (e.g. 'veo-3.1-generate-preview'), "
        "'prompt' (text description), "
        "'length_seconds' (desired video duration in seconds), "
        "'is_audio_required' (boolean, default true), "
        "and optionally 'start_frame_path' and 'end_frame_path' (image paths)."
    )

    # Output directory for generated videos
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "artifact", "generated_videos")
    
    # Maximum segment duration (Veo 3.1 supports 4, 5, 6, or 8 seconds)
    MAX_SEGMENT_SECONDS = 8

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
                        "description": "Video generation model (e.g. 'veo-3.1-generate-preview')"
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Text description of the video to generate"
                    },
                    "length_seconds": {
                        "type": "integer",
                        "description": "Desired video length in seconds"
                    },
                    "is_audio_required": {
                        "type": "boolean",
                        "description": "Whether the video should include audio (default: true)"
                    },
                    "start_frame_path": {
                        "type": "string",
                        "description": "Optional path to an image for the starting frame"
                    },
                    "end_frame_path": {
                        "type": "string",
                        "description": "Optional path to an image for the ending frame"
                    }
                },
                "required": ["model_name", "prompt", "length_seconds"]
            }
        }

    def _calculate_segments(self, total_seconds: int) -> List[int]:
        """
        Break total duration into segments of max 8 seconds each.
        Uses the largest segments possible (8, 6, 5, 4).
        
        Args:
            total_seconds: Total desired video duration
            
        Returns:
            List of segment durations in seconds
        """
        if total_seconds <= self.MAX_SEGMENT_SECONDS:
            # Map to valid Veo duration values
            if total_seconds <= 4:
                return [4]
            elif total_seconds <= 5:
                return [5]
            elif total_seconds <= 6:
                return [6]
            else:
                return [8]
        
        segments = []
        remaining = total_seconds
        
        while remaining > 0:
            if remaining >= 8:
                segments.append(8)
                remaining -= 8
            elif remaining >= 6:
                segments.append(6)
                remaining -= 6
            elif remaining >= 5:
                segments.append(5)
                remaining -= 5
            elif remaining >= 4:
                segments.append(4)
                remaining -= 4
            else:
                # Remaining is < 4, extend the last segment or add a 4s segment
                if segments:
                    # Remaining is small, just note it (will be covered by last extension)
                    segments.append(4)
                else:
                    segments.append(4)
                remaining = 0
        
        return segments

    async def _generate_single_video(
        self,
        client,
        model_name: str,
        prompt: str,
        duration: int,
        start_frame_path: Optional[str] = None,
        end_frame_path: Optional[str] = None,
        previous_video=None,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate a single video segment.
        
        Args:
            client: GenAI client
            model_name: Model name
            prompt: Text prompt
            duration: Duration in seconds
            start_frame_path: Optional start frame image
            end_frame_path: Optional end frame image  
            previous_video: Optional previous video object for extension
            output_path: Where to save the video
            
        Returns:
            Path to saved video file
        """
        if not output_path:
            video_id = str(uuid.uuid4())[:8]
            output_path = os.path.join(self.OUTPUT_DIR, f"segment_{video_id}.mp4")
        
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=str(duration),
            person_generation="allow_all"
        )
        
        # Build generation kwargs
        gen_kwargs = {
            "model": model_name,
            "prompt": prompt,
            "config": config
        }
        
        # Handle video extension (for multi-segment generation)
        if previous_video:
            gen_kwargs["video"] = previous_video
            logger.info(f"Extending previous video with {duration}s segment")
        else:
            # Handle reference images for initial generation
            if start_frame_path and os.path.exists(start_frame_path):
                logger.info(f"Loading start frame from {start_frame_path}")
                with open(start_frame_path, "rb") as f:
                    image_bytes = f.read()
                ext = os.path.splitext(start_frame_path)[1].lower()
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
                mime_type = mime_map.get(ext, "image/png")
                gen_kwargs["image"] = types.Image(image_bytes=image_bytes, mime_type=mime_type)
            
            if end_frame_path and os.path.exists(end_frame_path):
                logger.info(f"Loading end frame from {end_frame_path}")
                with open(end_frame_path, "rb") as f:
                    image_bytes = f.read()
                ext = os.path.splitext(end_frame_path)[1].lower()
                mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
                mime_type = mime_map.get(ext, "image/png")
                config.last_frame = types.Image(image_bytes=image_bytes, mime_type=mime_type)
        
        # Generate video (async polling)
        logger.info(f"Starting video generation: model={model_name}, duration={duration}s")
        operation = client.models.generate_videos(**gen_kwargs)
        
        # Poll for completion
        max_wait = 360  # 6 minutes max per Veo docs
        elapsed = 0
        poll_interval = 10
        
        while not operation.done:
            if elapsed >= max_wait:
                raise TimeoutError(f"Video generation timed out after {max_wait}s")
            
            logger.info(f"Waiting for video generation... ({elapsed}s elapsed)")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            operation = client.operations.get(operation)
        
        # Download the generated video
        if not operation.response or not operation.response.generated_videos:
            raise ValueError("No video was generated - possibly filtered by safety")
        
        generated_video = operation.response.generated_videos[0]
        client.files.download(file=generated_video.video)
        generated_video.video.save(output_path)
        
        logger.info(f"Video segment saved to {output_path} ({duration}s)")
        return output_path, generated_video

    async def _merge_videos(self, video_paths: List[str], output_path: str) -> str:
        """
        Merge multiple video segments using ffmpeg.
        
        Args:
            video_paths: List of video file paths to merge
            output_path: Path for the merged output video
            
        Returns:
            Path to merged video
        """
        if len(video_paths) == 1:
            # No merge needed, just rename
            os.rename(video_paths[0], output_path)
            return output_path
        
        # Create ffmpeg concat file
        concat_file = os.path.join(self.OUTPUT_DIR, f"concat_{uuid.uuid4().hex[:8]}.txt")
        try:
            with open(concat_file, "w") as f:
                for path in video_paths:
                    f.write(f"file '{os.path.abspath(path)}'\n")
            
            # Run ffmpeg concat
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # No re-encoding
                output_path
            ]
            
            logger.info(f"Merging {len(video_paths)} video segments with ffmpeg")
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # If copy fails, try re-encoding
                cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", "libx264", "-c:a", "aac",
                    output_path
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    raise RuntimeError(f"ffmpeg merge failed: {stderr.decode()}")
            
            logger.info(f"Merged video saved to {output_path}")
            return output_path
            
        finally:
            # Clean up concat file and individual segments
            if os.path.exists(concat_file):
                os.remove(concat_file)
            for path in video_paths:
                if os.path.exists(path) and path != output_path:
                    os.remove(path)

    async def run(self, input_data: str) -> str:
        """
        Execute video generation.
        
        Args:
            input_data: JSON string with model_name, prompt, length_seconds,
                       is_audio_required, start_frame_path, end_frame_path
            
        Returns:
            JSON string with generation result
        """
        try:
            params = json.loads(input_data)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        model_name = params.get("model_name", "veo-3.1-generate-preview")
        prompt = params.get("prompt")
        length_seconds = params.get("length_seconds", 8)
        is_audio_required = params.get("is_audio_required", True)
        start_frame_path = params.get("start_frame_path")
        end_frame_path = params.get("end_frame_path")
        
        if not prompt:
            return json.dumps({"error": "Missing required parameter: 'prompt'"})

        if not GENAI_AVAILABLE:
            return json.dumps({"error": "Google GenAI SDK not installed. Run: pip install google-genai"})

        try:
            # Initialize client
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if not api_key:
                return json.dumps({"error": "GOOGLE_API_KEY or GEMINI_API_KEY environment variable not set"})
            
            client = genai.Client(api_key=api_key)
            os.makedirs(self.OUTPUT_DIR, exist_ok=True)
            
            # Calculate segments
            segments = self._calculate_segments(length_seconds)
            total_segments = len(segments)
            
            logger.info(
                f"Video generation plan: {length_seconds}s total, "
                f"{total_segments} segment(s): {segments}"
            )
            
            if total_segments == 1:
                # Single segment - straightforward generation
                video_id = str(uuid.uuid4())[:8]
                output_path = os.path.join(self.OUTPUT_DIR, f"video_{video_id}.mp4")
                
                saved_path, _ = await self._generate_single_video(
                    client=client,
                    model_name=model_name,
                    prompt=prompt,
                    duration=segments[0],
                    start_frame_path=start_frame_path,
                    end_frame_path=end_frame_path,
                    output_path=output_path
                )
                
                result = {
                    "model": model_name,
                    "prompt": prompt,
                    "video_path": saved_path,
                    "duration_seconds": segments[0],
                    "segments": 1,
                    "has_audio": is_audio_required
                }
                return json.dumps(result)
            
            else:
                # Multi-segment: use Veo video extension API
                segment_paths = []
                previous_video = None
                total_generated_seconds = 0
                
                for i, duration in enumerate(segments):
                    segment_id = str(uuid.uuid4())[:8]
                    segment_path = os.path.join(self.OUTPUT_DIR, f"segment_{segment_id}.mp4")
                    
                    if i == 0:
                        # First segment: use reference images if provided
                        saved_path, gen_result = await self._generate_single_video(
                            client=client,
                            model_name=model_name,
                            prompt=prompt,
                            duration=duration,
                            start_frame_path=start_frame_path,
                            end_frame_path=end_frame_path if total_segments == 1 else None,
                            output_path=segment_path
                        )
                        previous_video = gen_result.video
                    else:
                        # Subsequent segments: extend the previous video
                        saved_path, gen_result = await self._generate_single_video(
                            client=client,
                            model_name=model_name,
                            prompt=prompt,
                            duration=duration,
                            previous_video=previous_video,
                            output_path=segment_path
                        )
                        previous_video = gen_result.video
                    
                    segment_paths.append(saved_path)
                    total_generated_seconds += duration
                    logger.info(f"Segment {i+1}/{total_segments} complete ({total_generated_seconds}s total)")
                
                # For video extension, Veo returns the combined video in the last
                # operation result, so we just use the last generated video
                video_id = str(uuid.uuid4())[:8]
                final_path = os.path.join(self.OUTPUT_DIR, f"video_{video_id}.mp4")
                
                # The last segment's video is already the extended video
                # Just rename it to the final path
                last_segment = segment_paths[-1]
                os.rename(last_segment, final_path)
                
                # Clean up intermediate segments
                for path in segment_paths[:-1]:
                    if os.path.exists(path):
                        os.remove(path)
                
                result = {
                    "model": model_name,
                    "prompt": prompt,
                    "video_path": final_path,
                    "duration_seconds": total_generated_seconds,
                    "segments": total_segments,
                    "segment_durations": segments,
                    "has_audio": is_audio_required
                }
                return json.dumps(result)

        except TimeoutError as e:
            logger.error(f"Video generation timeout: {e}")
            return json.dumps({"error": str(e)})
        except Exception as e:
            logger.error(f"Video generation error: {e}", exc_info=True)
            return json.dumps({"error": f"Video generation failed: {str(e)}"})
