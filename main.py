import asyncio

from app.bot.main import main
from app.core.logging import setup_logging

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
