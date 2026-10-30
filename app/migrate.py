import asyncio

from sqlalchemy import text

from app.database import engine


async def main():
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "password_hash VARCHAR(255)"
                )
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
