import io
from datetime import datetime, timedelta, timezone

from app.repository.admin import export_users_tasks_to_excel
from app.db.session import connection

MSC_TZ = timezone(timedelta(hours=3))


def _ekb_day_range() -> tuple[datetime, datetime]:
    """
    Интервал прошедшего дня по Москве:
    вчера 00:00 — сегодня 00:00
    """
    now = datetime.now(MSC_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    return yesterday_start, today_start


@connection()
async def export_daily_tasks_excel(*, session) -> io.BytesIO:
    date_from, date_to = _ekb_day_range()

    return await export_users_tasks_to_excel(
        date_from=date_from,
        date_to=date_to,
    )
