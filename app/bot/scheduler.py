from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timezone, timedelta

from aiogram import Bot
from app.bot.service.daily_report import send_daily_tasks_report
from app.bot.service.rejected_cleanup import run_rejected_archive

EKB_TZ = timezone(timedelta(hours=5))


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=EKB_TZ)

    scheduler.add_job(
        send_daily_tasks_report,
        trigger=CronTrigger(hour=0, minute=0),
        args=[bot],
        id="daily_tasks_report",
        replace_existing=True,
    )
    scheduler.add_job(
        run_rejected_archive,
        trigger=CronTrigger(hour=0, minute=5),
        id="archive_rejected_assignments",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler
