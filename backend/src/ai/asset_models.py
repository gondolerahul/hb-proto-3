"""
SQLAlchemy models for Media & Asset Management and Call Intelligence.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey,
    Numeric, JSON, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base


class Asset(Base):
    """
    Stores metadata and file paths for all system-generated media assets.
    Storage path: assets/{tenant_id}/{campaign_id}/{asset_type}/{YYYY-MM-DD}/{file_name}
    """
    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("execution_runs.id"), nullable=True)

    # File info
    file_type = Column(String(20), nullable=False)       # recordings | images | videos
    file_name = Column(String(500), nullable=False)
    file_path = Column(Text(), nullable=False)            # Relative path from assets root
    file_size = Column(BigInteger, nullable=True)         # bytes
    duration_seconds = Column(Integer, nullable=True)     # For audio/video
    mime_type = Column(String(100), nullable=True)
    asset_metadata = Column(JSON, nullable=True)          # Extra info (dimensions, call SID, etc.)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    company = relationship("Company")
    campaign = relationship("HierarchicalEntity", foreign_keys=[campaign_id])
    agent = relationship("HierarchicalEntity", foreign_keys=[agent_id])
    run = relationship("ExecutionRun")

    # Back-reference from call_content
    call_contents = relationship("CallContent", back_populates="audio_asset")


class CallLog(Base):
    """
    Telephony call metadata for call intelligence and reporting.
    """
    __tablename__ = "call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    voice_session_id = Column(UUID(as_uuid=True), nullable=True)   # Ref to voice_sessions (no FK: different module)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=True)

    direction = Column(String(20), nullable=True)       # inbound | outbound
    status = Column(String(30), nullable=True)          # completed | failed | no-answer
    duration_seconds = Column(Integer, nullable=True)
    from_number = Column(String(30), nullable=True)
    to_number = Column(String(30), nullable=True)
    provider = Column(String(30), nullable=True)        # twilio | tata_tele
    call_cost_usd = Column(Numeric(10, 6), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    company = relationship("Company")
    agent = relationship("HierarchicalEntity")
    content = relationship("CallContent", back_populates="call_log", uselist=False)


class CallContent(Base):
    """
    Transcript and summary for a call, with a reference to the audio recording asset.
    """
    __tablename__ = "call_content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_log_id = Column(UUID(as_uuid=True), ForeignKey("call_logs.id"), nullable=False)
    audio_asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True)

    transcript_text = Column(Text, nullable=True)
    summary_text = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=True)    # positive | neutral | negative
    content_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    call_log = relationship("CallLog", back_populates="content")
    audio_asset = relationship("Asset", back_populates="call_contents")
