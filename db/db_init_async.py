import constants
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from db.models import Base

async_engine = create_async_engine(
    f'postgresql+asyncpg://{constants.POSTGRES_USER}:{constants.POSTGRES_PASSWORD}@{constants.POSTGRES_HOST}/{constants.SALON_DB}',
    echo=False,
)
Session_async = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def create_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
