# Tools package initialization
"""
HireBuddha AI Tools Package

This package contains production-ready tool implementations for:
- Calculator: Safe mathematical expression evaluation
- Search: Real web search using DuckDuckGo
- Email: IMAP/SMTP email tools (ingest, classify, draft, send)
- Image Generation: AI image generation via Gemini API
- Video Generation: AI video generation via Veo 3.1 API
"""

from src.ai.tools.base import Tool, ToolRegistry
from src.ai.tools.calculator import CalculatorTool
from src.ai.tools.search import WebSearchTool
from src.ai.tools.excel import ExcelTool
from src.ai.tools.scraper import ScraperTool
from src.ai.tools.pdf_generator import PDFGeneratorTool
from src.ai.tools.file_writer import FileWriterTool
from src.ai.tools.email_tool import EmailIngestTool, EmailClassifyTool, EmailDraftTool, EmailSendTool
from src.ai.tools.image_generation import ImageGenerationTool
from src.ai.tools.video_generation import VideoGenerationTool

# Register all default tools
ToolRegistry.register(CalculatorTool())
ToolRegistry.register(WebSearchTool())
ToolRegistry.register(ExcelTool())
ToolRegistry.register(ScraperTool())
ToolRegistry.register(PDFGeneratorTool())
ToolRegistry.register(FileWriterTool())

# Email tools (IMAP/SMTP)
ToolRegistry.register(EmailIngestTool())
ToolRegistry.register(EmailClassifyTool())
ToolRegistry.register(EmailDraftTool())
ToolRegistry.register(EmailSendTool())

# Media generation tools
ToolRegistry.register(ImageGenerationTool())
ToolRegistry.register(VideoGenerationTool())

__all__ = [
    "Tool",
    "ToolRegistry",
    "CalculatorTool", 
    "WebSearchTool",
    "ExcelTool",
    "ScraperTool",
    "PDFGeneratorTool",
    "FileWriterTool",
    "EmailIngestTool",
    "EmailClassifyTool",
    "EmailDraftTool",
    "EmailSendTool",
    "ImageGenerationTool",
    "VideoGenerationTool",
]
