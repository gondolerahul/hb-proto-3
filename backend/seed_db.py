import asyncio
import sys
import os

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from src.common.config import settings
from src.auth.models import User, Tenant, Partner
from src.common.security import get_password_hash

# Define database URL
DATABASE_URL = settings.DATABASE_URL

# Create async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Seeding database...")
        
        # 1. Create App Admin
        # Check if exists
        result = await db.execute(select(User).filter(User.email == "admin@hb.com"))
        admin_user = result.scalars().first()
        
        if not admin_user:
            print("Creating App Admin...")
            # Create a System Tenant for Admin
            system_tenant = Tenant(name="HireBuddha System", status="active")
            db.add(system_tenant)
            await db.flush()
            
            admin_user = User(
                email="admin@hb.com",
                full_name="Platform Administrator",
                hashed_password=get_password_hash("adminpass"),
                tenant_id=system_tenant.id,
                role="app_admin",
                is_active=True,
                is_verified=True
            )
            db.add(admin_user)
            await db.commit()
            print("App Admin created.")
        else:
            print("App Admin already exists.")

        # 2. Create Partner Admin
        result = await db.execute(select(User).filter(User.email == "partner@tech.com"))
        partner_user = result.scalars().first()
        
        if not partner_user:
            print("Creating Partner Admin...")
            
            # Create Partner Entity
            partner = Partner(name="TechSolutions Inc")
            db.add(partner)
            await db.flush()
            
            # Create Tenant for Partner Admin
            partner_tenant = Tenant(
                name="TechSolutions Admin Workspace", 
                status="active",
                partner_id=partner.id
            )
            db.add(partner_tenant)
            await db.flush()
            
            partner_user = User(
                email="partner@tech.com",
                full_name="Partner Administrator",
                hashed_password=get_password_hash("partnerpass"),
                tenant_id=partner_tenant.id,
                role="partner_admin",
                is_active=True,
                is_verified=True
            )
            db.add(partner_user)
            
            # Link user to partner as admin
            partner.admin_user_id = partner_user.id
            db.add(partner) # Update partner
            
            await db.commit()
            print("Partner Admin created.")
        else:
            print("Partner Admin already exists.")
            
    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_data())
