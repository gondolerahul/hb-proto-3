from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from src.auth.models import User, Tenant, Partner
from src.tenant.schemas import PartnerCreate, TenantCreate, TenantUpdate, UserInvite
from src.common.security import get_password_hash

async def create_partner(db: AsyncSession, partner_in: PartnerCreate):
    # Check if admin user exists
    result = await db.execute(select(User).filter(User.email == partner_in.admin_email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Admin email already registered")

    # Create Partner
    new_partner = Partner(name=partner_in.name)
    db.add(new_partner)
    await db.flush()

    # Create Partner Admin User (linked to a dummy tenant or special system tenant? 
    # For now, let's create a 'Partner Workspace' tenant for them)
    partner_tenant = Tenant(name=f"{partner_in.name} Workspace", partner_id=new_partner.id)
    db.add(partner_tenant)
    await db.flush()

    hashed_password = get_password_hash(partner_in.admin_password)
    new_user = User(
        email=partner_in.admin_email,
        full_name=partner_in.admin_name,
        hashed_password=hashed_password,
        tenant_id=partner_tenant.id,
        role="partner_admin"
    )
    db.add(new_user)
    await db.flush()

    new_partner.admin_user_id = new_user.id
    await db.commit()
    await db.refresh(new_partner)
    return new_partner

async def create_tenant_for_partner(db: AsyncSession, partner_id: str, tenant_in: TenantCreate):
    # Check if user exists
    result = await db.execute(select(User).filter(User.email == tenant_in.admin_email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Admin email already registered")

    # Create Tenant
    new_tenant = Tenant(name=tenant_in.name, partner_id=partner_id)
    db.add(new_tenant)
    await db.flush()

    # Create Tenant Admin
    hashed_password = get_password_hash(tenant_in.admin_password)
    new_user = User(
        email=tenant_in.admin_email,
        full_name=tenant_in.admin_name,
        hashed_password=hashed_password,
        tenant_id=new_tenant.id,
        role="tenant_admin"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant

async def get_tenants(db: AsyncSession, partner_id: str = None):
    query = select(Tenant)
    if partner_id:
        query = query.filter(Tenant.partner_id == partner_id)
    result = await db.execute(query)
    return result.scalars().all()

async def update_tenant(db: AsyncSession, tenant_id: str, tenant_update: TenantUpdate):
    result = await db.execute(select(Tenant).filter(Tenant.id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if tenant_update.status:
        tenant.status = tenant_update.status
    if tenant_update.name:
        tenant.name = tenant_update.name
    
    await db.commit()
    await db.refresh(tenant)
    return tenant
