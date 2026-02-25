import asyncio
from datetime import timedelta
from sqlalchemy import select
import sys
import os

# Add parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.database import AsyncSessionLocal
from src.auth.models import User
from src.auth.service import create_access_token

async def get_token():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == "admin@hb.com"))
        user = result.scalar_one_or_none()
        
        if user:
            # Generate token valid for 1 hour
            access_token = create_access_token(
                data={"sub": user.email},
                expires_delta=timedelta(hours=1)
            )
            print(f"TOKEN: {access_token}")
        else:
            print("User not found")

if __name__ == "__main__":
    asyncio.run(get_token())
