from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import connection
from app.models.city import City


@connection()
async def get_all_cities(
    *,
    session: AsyncSession,
) -> list[City]:
    """
    Возвращает список доступных городов.

    Args:
        session (AsyncSession): Сессия базы данных.

    Returns:
        list[City]: Список городов.
    """
    result = await session.execute(select(City).order_by(City.name))
    return result.scalars().all()
