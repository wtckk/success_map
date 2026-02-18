import logging

from app.repository.task import (
    archive_rejected_assignments,
    archive_assignment_by_id,
    delete_unsubmitted_tasks,
)

logger = logging.getLogger(__name__)


async def run_rejected_archive() -> None:
    logger.info("start run_rejected_archive()")

    count = await archive_rejected_assignments()
    if count:
        logger.info("Rejected assignments archived: %s", count)


async def archive_rejected_later(assignment_id: int) -> None:
    logger.info(
        "Running delayed archive for rejected assignment %s",
        assignment_id,
    )

    archived = await archive_assignment_by_id(assignment_id=assignment_id)

    if archived:
        logger.info(
            "Assignment %s archived after rejection delay",
            assignment_id,
        )


async def run_unsubmitted_cleanup() -> None:
    logger.info("Start cleanup of unsubmitted tasks")

    deleted = await delete_unsubmitted_tasks()

    if deleted:
        logger.info(
            "Deleted %s unsubmitted tasks with full history",
            deleted,
        )
