import asyncio
import logging
from app.core.database import engine, Base
from app.models import *  # ensure all models are imported

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def init_tables():
    logger.info("Connecting to database and creating tables...")
    async with engine.begin() as conn:
        logger.info("Running create_all...")
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tables created successfully.")


if __name__ == "__main__":
    asyncio.run(init_tables())
