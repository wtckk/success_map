import logging
from aiogram import Bot
from aiogram.types import BufferedInputFile

from app.core.settings import settings
from app.repository.task_repository_daily import (
    export_daily_tasks_excel,
    export_weekly_tasks_excel,
)

logger = logging.getLogger(__name__)


async def send_daily_tasks_report(bot: Bot) -> None:
    logger.info("start send_daily_tasks_report")

    buffer = await export_daily_tasks_excel()
    data = buffer.read()

    if not data:
        logger.info("Daily report: empty file")
        return

    for admin_id in settings.admin_id_list:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=BufferedInputFile(
                    data,
                    filename="daily_tasks_report.xlsx",
                ),
                caption="📊 Отчёт по заданиям за прошедший день",
            )
        except Exception:
            logger.exception("Failed to send daily report to admin %s", admin_id)


async def send_weekly_tasks_report(bot: Bot) -> None:
    logger.info("start send_weekly_tasks_report")

    buffer = await export_weekly_tasks_excel()
    data = buffer.read()

    if not data:
        logger.info("Weekly report: empty file")
        return

    for admin_id in settings.admin_id_list:
        try:
            await bot.send_document(
                chat_id=admin_id,
                document=BufferedInputFile(
                    data,
                    filename="weekly_tasks_report.xlsx",
                ),
                caption="📊 Отчёт по заданиям за прошедшую неделю",
            )
        except Exception:
            logger.exception(
                "Failed to send weekly report to admin %s",
                admin_id,
            )
