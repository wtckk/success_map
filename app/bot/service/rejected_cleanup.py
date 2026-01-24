import logging

from app.repository.task import archive_rejected_assignments

logger = logging.getLogger(__name__)


async def run_rejected_archive() -> None:
    count = await archive_rejected_assignments()
    if count:
        logger.info("Rejected assignments archived: %s", count)
