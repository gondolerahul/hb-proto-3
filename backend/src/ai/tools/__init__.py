# Tools package initialization
"""
HireBuddha AI Tools Package

This package contains production-ready tool implementations for:
- Calculator, Search, Excel, Scraper, PDF, File Writer
- Email (IMAP/SMTP), Image Gen, Video Gen, Sandbox
- Document CRUD (docx, pptx, xlsx)
- Social media tools (Phase 1, 2, 3)
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
from src.ai.tools.sandbox_executor import SandboxCodeTool
from src.ai.tools.terminal_tool import TerminalTool
from src.ai.tools.browser_tool import HeadlessBrowserTool
from src.ai.tools.docx_tool import DocxTool
from src.ai.tools.pptx_tool import PptxTool
from src.ai.tools.crm_tools import (
    GetCurrentDateTimeTool,
    WhatsAppSendTenantTool,
    GoogleCalendarCreateEventTool,
    CRMUpdateLeadTool,
)

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

# Sandbox execution tool (Ph-A: asyncio subprocess tier)
ToolRegistry.register(SandboxCodeTool())

# Terminal tool (shell command execution via sandbox)
ToolRegistry.register(TerminalTool())

# Headless browser tool (Playwright-based web interaction)
ToolRegistry.register(HeadlessBrowserTool())

# Document CRUD tools
ToolRegistry.register(DocxTool())
ToolRegistry.register(PptxTool())

# CRM integration tools (Real Estate tenant workflow)
ToolRegistry.register(GetCurrentDateTimeTool())
ToolRegistry.register(WhatsAppSendTenantTool())
ToolRegistry.register(GoogleCalendarCreateEventTool())
ToolRegistry.register(CRMUpdateLeadTool())

# Social media platform tools — Phase 1
from src.ai.tools.social import (
    LinkedInCreatePostTool, LinkedInGetAnalyticsTool,
    LinkedInManageCommentsTool, LinkedInGetProfileTool,
    TwitterCreatePostTool, TwitterSearchTool,
    TwitterGetMentionsTool, TwitterGetAnalyticsTool,
    FacebookCreatePostTool, FacebookGetInsightsTool,
    FacebookManageCommentsTool, FacebookSendMessageTool,
    InstagramPublishMediaTool, InstagramGetInsightsTool,
    InstagramManageCommentsTool, InstagramDiscoverHashtagsTool,
    GoogleAdsCreateCampaignTool, GoogleAdsReportTool,
    GoogleAdsManageKeywordsTool, GoogleAdsGetAdGroupsTool,
    # Phase 2
    YouTubeUploadVideoTool, YouTubeManagePlaylistsTool,
    YouTubeGetAnalyticsTool, YouTubeManageCommentsTool,
    TikTokPublishVideoTool, TikTokGetVideosTool,
    TikTokGetAnalyticsTool, TikTokManageCommentsTool,
    RedditCreatePostTool, RedditSearchTool,
    RedditManageCommentsTool, RedditGetAnalyticsTool,
    QuoraSearchQuestionsTool, QuoraPostAnswerTool,
    QuoraGetSpacesTool, QuoraGetAnalyticsTool,
    PinterestCreatePinTool, PinterestManageBoardsTool,
    PinterestGetAnalyticsTool, PinterestSearchPinsTool,
    MetaAdsCreateCampaignTool, MetaAdsManageAdsetsTool,
    MetaAdsReportTool, MetaAdsManageAudiencesTool,
    LinkedInAdsCreateCampaignTool, LinkedInAdsManageCreativesTool,
    LinkedInAdsReportTool, LinkedInAdsManageAudiencesTool,
    # Phase 3
    LinkedInSalesSearchLeadsTool, LinkedInSalesGetLeadTool,
    LinkedInSalesSaveLeadTool, LinkedInSalesGetListsTool,
    YouTubeAdsCreateCampaignTool, YouTubeAdsManageAdGroupsTool,
    YouTubeAdsReportTool, YouTubeAdsManageTargetingTool,
    XAdsCreateCampaignTool, XAdsManageLineItemsTool,
    XAdsReportTool, XAdsManageAudiencesTool,
    SnapchatAdsCreateCampaignTool, SnapchatAdsManageAdSquadsTool,
    SnapchatAdsReportTool, SnapchatAdsManageAudiencesTool,
)

# Phase 1 registrations
ToolRegistry.register(LinkedInCreatePostTool())
ToolRegistry.register(LinkedInGetAnalyticsTool())
ToolRegistry.register(LinkedInManageCommentsTool())
ToolRegistry.register(LinkedInGetProfileTool())
ToolRegistry.register(TwitterCreatePostTool())
ToolRegistry.register(TwitterSearchTool())
ToolRegistry.register(TwitterGetMentionsTool())
ToolRegistry.register(TwitterGetAnalyticsTool())
ToolRegistry.register(FacebookCreatePostTool())
ToolRegistry.register(FacebookGetInsightsTool())
ToolRegistry.register(FacebookManageCommentsTool())
ToolRegistry.register(FacebookSendMessageTool())
ToolRegistry.register(InstagramPublishMediaTool())
ToolRegistry.register(InstagramGetInsightsTool())
ToolRegistry.register(InstagramManageCommentsTool())
ToolRegistry.register(InstagramDiscoverHashtagsTool())
ToolRegistry.register(GoogleAdsCreateCampaignTool())
ToolRegistry.register(GoogleAdsReportTool())
ToolRegistry.register(GoogleAdsManageKeywordsTool())
ToolRegistry.register(GoogleAdsGetAdGroupsTool())

# Phase 2 registrations
ToolRegistry.register(YouTubeUploadVideoTool())
ToolRegistry.register(YouTubeManagePlaylistsTool())
ToolRegistry.register(YouTubeGetAnalyticsTool())
ToolRegistry.register(YouTubeManageCommentsTool())
ToolRegistry.register(TikTokPublishVideoTool())
ToolRegistry.register(TikTokGetVideosTool())
ToolRegistry.register(TikTokGetAnalyticsTool())
ToolRegistry.register(TikTokManageCommentsTool())
ToolRegistry.register(RedditCreatePostTool())
ToolRegistry.register(RedditSearchTool())
ToolRegistry.register(RedditManageCommentsTool())
ToolRegistry.register(RedditGetAnalyticsTool())
ToolRegistry.register(QuoraSearchQuestionsTool())
ToolRegistry.register(QuoraPostAnswerTool())
ToolRegistry.register(QuoraGetSpacesTool())
ToolRegistry.register(QuoraGetAnalyticsTool())
ToolRegistry.register(PinterestCreatePinTool())
ToolRegistry.register(PinterestManageBoardsTool())
ToolRegistry.register(PinterestGetAnalyticsTool())
ToolRegistry.register(PinterestSearchPinsTool())
ToolRegistry.register(MetaAdsCreateCampaignTool())
ToolRegistry.register(MetaAdsManageAdsetsTool())
ToolRegistry.register(MetaAdsReportTool())
ToolRegistry.register(MetaAdsManageAudiencesTool())
ToolRegistry.register(LinkedInAdsCreateCampaignTool())
ToolRegistry.register(LinkedInAdsManageCreativesTool())
ToolRegistry.register(LinkedInAdsReportTool())
ToolRegistry.register(LinkedInAdsManageAudiencesTool())

# Phase 3 registrations
ToolRegistry.register(LinkedInSalesSearchLeadsTool())
ToolRegistry.register(LinkedInSalesGetLeadTool())
ToolRegistry.register(LinkedInSalesSaveLeadTool())
ToolRegistry.register(LinkedInSalesGetListsTool())
ToolRegistry.register(YouTubeAdsCreateCampaignTool())
ToolRegistry.register(YouTubeAdsManageAdGroupsTool())
ToolRegistry.register(YouTubeAdsReportTool())
ToolRegistry.register(YouTubeAdsManageTargetingTool())
ToolRegistry.register(XAdsCreateCampaignTool())
ToolRegistry.register(XAdsManageLineItemsTool())
ToolRegistry.register(XAdsReportTool())
ToolRegistry.register(XAdsManageAudiencesTool())
ToolRegistry.register(SnapchatAdsCreateCampaignTool())
ToolRegistry.register(SnapchatAdsManageAdSquadsTool())
ToolRegistry.register(SnapchatAdsReportTool())
ToolRegistry.register(SnapchatAdsManageAudiencesTool())

# Meta-Agent tools (context-aware — use run_with_context)
from src.ai.tools.meta import (
    MetaRegistrySearchTool, MetaSchemaValidatorTool,
    MetaEntityCreatorTool, MetaEntityExecutorTool,
    MetaPlatformIntrospectTool,
)
ToolRegistry.register(MetaPlatformIntrospectTool())
ToolRegistry.register(MetaRegistrySearchTool())
ToolRegistry.register(MetaSchemaValidatorTool())
ToolRegistry.register(MetaEntityCreatorTool())
ToolRegistry.register(MetaEntityExecutorTool())

__all__ = [
    "Tool", "ToolRegistry",
    "CalculatorTool", "WebSearchTool", "ExcelTool", "ScraperTool",
    "PDFGeneratorTool", "FileWriterTool",
    "EmailIngestTool", "EmailClassifyTool", "EmailDraftTool", "EmailSendTool",
    "ImageGenerationTool", "VideoGenerationTool", "SandboxCodeTool", "TerminalTool",
    "HeadlessBrowserTool",
    "DocxTool", "PptxTool",
    # Phase 1 social
    "LinkedInCreatePostTool", "LinkedInGetAnalyticsTool",
    "LinkedInManageCommentsTool", "LinkedInGetProfileTool",
    "TwitterCreatePostTool", "TwitterSearchTool",
    "TwitterGetMentionsTool", "TwitterGetAnalyticsTool",
    "FacebookCreatePostTool", "FacebookGetInsightsTool",
    "FacebookManageCommentsTool", "FacebookSendMessageTool",
    "InstagramPublishMediaTool", "InstagramGetInsightsTool",
    "InstagramManageCommentsTool", "InstagramDiscoverHashtagsTool",
    "GoogleAdsCreateCampaignTool", "GoogleAdsReportTool",
    "GoogleAdsManageKeywordsTool", "GoogleAdsGetAdGroupsTool",
    # Phase 2 social
    "YouTubeUploadVideoTool", "YouTubeManagePlaylistsTool",
    "YouTubeGetAnalyticsTool", "YouTubeManageCommentsTool",
    "TikTokPublishVideoTool", "TikTokGetVideosTool",
    "TikTokGetAnalyticsTool", "TikTokManageCommentsTool",
    "RedditCreatePostTool", "RedditSearchTool",
    "RedditManageCommentsTool", "RedditGetAnalyticsTool",
    "QuoraSearchQuestionsTool", "QuoraPostAnswerTool",
    "QuoraGetSpacesTool", "QuoraGetAnalyticsTool",
    "PinterestCreatePinTool", "PinterestManageBoardsTool",
    "PinterestGetAnalyticsTool", "PinterestSearchPinsTool",
    "MetaAdsCreateCampaignTool", "MetaAdsManageAdsetsTool",
    "MetaAdsReportTool", "MetaAdsManageAudiencesTool",
    "LinkedInAdsCreateCampaignTool", "LinkedInAdsManageCreativesTool",
    "LinkedInAdsReportTool", "LinkedInAdsManageAudiencesTool",
    # Phase 3 social
    "LinkedInSalesSearchLeadsTool", "LinkedInSalesGetLeadTool",
    "LinkedInSalesSaveLeadTool", "LinkedInSalesGetListsTool",
    "YouTubeAdsCreateCampaignTool", "YouTubeAdsManageAdGroupsTool",
    "YouTubeAdsReportTool", "YouTubeAdsManageTargetingTool",
    "XAdsCreateCampaignTool", "XAdsManageLineItemsTool",
    "XAdsReportTool", "XAdsManageAudiencesTool",
    "SnapchatAdsCreateCampaignTool", "SnapchatAdsManageAdSquadsTool",
    "SnapchatAdsReportTool", "SnapchatAdsManageAudiencesTool",
    # CRM integration tools
    "GetCurrentDateTimeTool", "WhatsAppSendTenantTool",
    "GoogleCalendarCreateEventTool", "CRMUpdateLeadTool",
    # Meta-Agent tools
    "MetaPlatformIntrospectTool", "MetaRegistrySearchTool",
    "MetaSchemaValidatorTool", "MetaEntityCreatorTool",
    "MetaEntityExecutorTool",
]

