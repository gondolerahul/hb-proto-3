"""
Campaign models for bulk voice calling.

Stores campaign metadata, execution state, and call tracking.
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.common.database import Base


class Campaign(Base):
    """Voice calling campaign model."""
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("hierarchical_entities.id"), nullable=False)
    
    # Campaign details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Contact list
    total_contacts = Column(Integer, nullable=False, default=0)
    contact_list = Column(JSONB, nullable=False)  # Array of contact objects
    
    # Configuration
    provider = Column(String(20), nullable=False, default="twilio")  # 'twilio' | 'tata_tele'
    call_script_template = Column(Text, nullable=True)  # Custom script template
    
    # Scheduling
    scheduled_start = Column(DateTime, nullable=True)
    scheduled_end = Column(DateTime, nullable=True)
    
    # Throttling
    max_concurrent_calls = Column(Integer, nullable=False, default=5)
    max_calls_per_hour = Column(Integer, nullable=True)
    
    # Status
    status = Column(String(20), nullable=False, default="draft")  # draft | scheduled | running | paused | completed | failed
    
    # Execution tracking
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    calls_initiated = Column(Integer, nullable=False, default=0)
    calls_completed = Column(Integer, nullable=False, default=0)
    calls_failed = Column(Integer, nullable=False, default=0)
    
    # Results summary
    outcome_distribution = Column(JSONB, nullable=True)  # {"success": 10, "no_answer": 5, ...}
    
    # Metadata
    campaign_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    company = relationship("Company")
    created_by_user = relationship("User")
    agent = relationship("HierarchicalEntity")


class CampaignCall(Base):
    """Individual call within a campaign."""
    __tablename__ = "campaign_calls"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    voice_session_id = Column(UUID(as_uuid=True), ForeignKey("voice_sessions.id"), nullable=True)
    
    # Contact info
    contact_data = Column(JSONB, nullable=False)  # Phone, name, custom fields
    
    # Call status
    status = Column(String(20), nullable=False, default="pending")  # pending | calling | completed | failed | skipped
    call_sid = Column(String(100), nullable=True)
    
    # Outcome
    outcome = Column(String(50), nullable=True)  # success | no_answer | busy | failed | refused
    outcome_notes = Column(Text, nullable=True)
    
    # Timing
    scheduled_at = Column(DateTime, nullable=True)
    called_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=2)
    
    # Metadata
    call_metadata = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    campaign = relationship("Campaign")
    voice_session = relationship("VoiceSession")
