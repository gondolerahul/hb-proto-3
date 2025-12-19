import asyncio
import sys
import os

from sqlalchemy import text
from src.common.database import engine

async def drop_all():
    print("Dropping all tables with CASCADE...")
    async with engine.begin() as conn:
        # Drop all tables in the public schema using CASCADE
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO current_user;"))
    print("All tables dropped successfully.")

if __name__ == "__main__":
    asyncio.run(drop_all())
