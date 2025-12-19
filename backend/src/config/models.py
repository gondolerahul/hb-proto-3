import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.common.database import Base

class IntegrationRegistry(Base):
    __tablename__ = "integration_registry"
    __table_args__ = (
        UniqueConstraint('company_id', 'service_sku', name='uq_integration_company_sku'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    provider_name = Column(String, nullable=False)  # e.g., OpenAI, Twilio
    model_name = Column(String, nullable=True)     # e.g., gpt-4o
    service_sku = Column(String, nullable=False)   # e.g., gpt-4o-in
    component_type = Column(String, nullable=False) # input_token, output_token, analysis, minute, character, flat_fee
    encrypted_api_key = Column(Text, nullable=True)
    internal_cost = Column(Numeric(18, 6), nullable=False)
    cost_unit = Column(String, nullable=False)      # e.g., 1M Tokens, 1 Image
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = relationship("src.auth.models.Company")
