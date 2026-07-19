"""
ai.tenant_schema — the per-tenant business data plane (Increment 1 / SCH).

The predefined HireBuddha Business Schema (27 canonical objects) lives in a
per-tenant database — a dedicated container in prod, a per-tenant schema in
dev/test — reached through one record-service codepath. KB + CORTEX memory
stay in the control plane (v3.0.6 decision).

Design: docs/product-road-map/increment-1/03_sch_tenant_schema.md + 03a_hbs_spine.md
(authority: product_technical_documentation.md §10, §19, §23-§24).
"""
from src.ai.tenant_schema.models import (
    TenantBase,
    TenantEntityDef,
    TenantRecord,
    TenantRecordLink,
)

__all__ = ["TenantBase", "TenantEntityDef", "TenantRecord", "TenantRecordLink"]
