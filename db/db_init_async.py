import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from db.models import Base

load_dotenv('/etc/env/db.env')

user = os.getenv('POSTGRES_user')
password = os.getenv('POSTGRES_password')
db = os.getenv('SALON_db')
host = 'localhost'

async_engine = create_async_engine(f'postgresql+asyncpg://{user}:{password}@{host}/{db}', echo=False)
Session_async = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
