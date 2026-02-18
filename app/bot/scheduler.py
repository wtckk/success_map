from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import timezone, timedelta

from aiogram import Bot
from app.bot.service.daily_report import (
    send_daily_tasks_report,
    send_weekly_tasks_report,
)
from app.bot.service.rejected_cleanup import (
    run_rejected_archive,
    run_unsubmitted_cleanup,
)

MSC_TZ = timezone(timedelta(hours=3))


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(
        timezone=MSC_TZ,
        job_defaults={
            "misfire_grace_time": 600,
            "coalesce": True,
        },
    )
    scheduler.add_job(
        send_daily_tasks_report,
        trigger=CronTrigger(
            hour=0,
            minute=0,
            timezone=MSC_TZ,
        ),
        args=[bot],
        id="daily_tasks_report",
        replace_existing=True,
    )
    scheduler.add_job(
        run_rejected_archive,
        trigger=CronTrigger(
            hour=0,
            minute=5,
            timezone=MSC_TZ,
        ),
        id="archive_rejected_assignments",
        replace_existing=True,
    )

    scheduler.add_job(
        send_weekly_tasks_report,
        trigger=CronTrigger(
            day_of_week="mon",
            hour=0,
            minute=10,
            timezone=MSC_TZ,
        ),
        args=[bot],
        id="weekly_tasks_report",
        replace_existing=True,
    )

    scheduler.add_job(
        run_unsubmitted_cleanup,
        trigger=CronTrigger(
            hour=5,
            minute=0,
            timezone=MSC_TZ,
        ),
        id="cleanup_unsubmitted_tasks",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler
