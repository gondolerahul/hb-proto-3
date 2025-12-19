import asyncio
import sys
import os

# Add the current directory to sys.path to make imports work
sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from src.common.config import settings
from src.auth.models import User, Company
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
        
        # 1. Create App Company & Admin
        result = await db.execute(select(Company).filter(Company.type == "APP"))
        app_company = result.scalars().first()
        
        if not app_company:
            print("Creating App Company...")
            app_company = Company(
                name="HireBuddha Platform",
                type="APP",
                status="active"
            )
            db.add(app_company)
            await db.flush()
            
            # Create App Admin
            print("Creating App Admin...")
            admin_user = User(
                email="admin@hb.com",
                full_name="Platform Administrator",
                hashed_password=get_password_hash("adminpass"),
                company_id=app_company.id,
                role="app_admin",
                is_active=True,
                is_verified=True
            )
            db.add(admin_user)
            await db.commit()
            print("App Admin created.")
        else:
            print("App Company already exists.")

        # 2. Create Partner Company & Admin
        result = await db.execute(select(User).filter(User.email == "partner@tech.com"))
        partner_user = result.scalars().first()
        
        if not partner_user:
            print("Creating Partner Company...")
            partner_company = Company(
                name="TechSolutions Inc",
                type="PARTNER",
                parent_id=app_company.id,
                status="active"
            )
            db.add(partner_company)
            await db.flush()
            
            print("Creating Partner Admin...")
            partner_user = User(
                email="partner@tech.com",
                full_name="Partner Administrator",
                hashed_password=get_password_hash("partnerpass"),
                company_id=partner_company.id,
                role="partner_admin",
                is_active=True,
                is_verified=True
            )
            db.add(partner_user)
            await db.commit()
            print("Partner Admin created.")
        else:
            print("Partner Admin already exists.")
            
    print("Seeding complete.")

if __name__ == "__main__":
    asyncio.run(seed_data())
