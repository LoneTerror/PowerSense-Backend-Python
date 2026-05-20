import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

# 1. LOAD THE ENV IMMEDIATELY (Before anything else happens)
load_dotenv()

# 2. Fetch the URL securely
DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Fail loudly and visibly if the .env file is missing or broken
if not DATABASE_URL:
    raise ValueError("🚨 CRITICAL: DATABASE_URL is missing! Check your .env file.")

# Create the engine using the secure URL
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

async def get_db():
    """Dependency injection for database sessions."""
    async with AsyncSessionLocal() as session:
        yield session