import asyncio

from crud.database import Base, engine
from crud.models import User


async def create_tables():
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_tables())