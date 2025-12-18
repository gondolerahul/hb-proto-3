import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from src.common.database import Base

class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_key = Column(String, unique=True, nullable=False)  # e.g., gpt-4
    model_name = Column(String, nullable=False)  # e.g., GPT-4 Turbo
    provider = Column(String, nullable=False)  # e.g., openai
    model_type = Column(String, nullable=False)  # text, image, video
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemConfig(Base):
    __tablename__ = "system_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String, unique=True, nullable=False)  # e.g., openai_api_key
    value = Column(Text, nullable=False)  # Encrypted value
    is_encrypted = Column(Boolean, default=True)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
