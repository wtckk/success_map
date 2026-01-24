import uuid
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, aliased

from app.core.settings import settings
from app.db.session import connection
from app.models import Task
from app.models.user import User, UserApprovalStatus
from app.models.task_assignment import TaskAssignment, TaskAssignmentStatus
from app.models.user_approval_admin_message import UserApprovalAdminMessage

logger = logging.getLogger(__name__)


@connection()
async def get_user_by_tg_id(
    tg_id: int,
    *,
    session,
) -> User | None:
    """
    Возвращает пользователя по Telegram ID с загруженными связями.
    """
    stmt = (
        select(User)
        .where(User.tg_id == tg_id)
        .options(
            selectinload(User.referrer),
            selectinload(User.city),
        )
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@connection()
async def get_user_by_id(
    user_id: int,
    *,
    session,
) -> User | None:
    """
    Возвращает пользователя по Telegram ID с загруженными связями.
    """
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.referrer),
            selectinload(User.city),
        )
    )

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


@connection()
async def is_user_blocked(
    session: AsyncSession,
    *,
    tg_id: int,
) -> bool:
    result = await session.execute(select(User.is_blocked).where(User.tg_id == tg_id))
    return bool(result.scalar())


@connection()
async def get_user_id_by_tg_id(
    tg_id: int,
    *,
    session: AsyncSession,
) -> uuid.UUID | None:
    """
    Возвращает UUID пользователя по Telegram ID.

    Args:
        tg_id (int): Telegram ID пользователя.
        session (AsyncSession): Сессия базы данных.

    Returns:
        UUID | None: UUID пользователя или None.
    """
    result = await session.execute(select(User.id).where(User.tg_id == tg_id))
    return result.scalar_one_or_none()


@connection()
async def create_user(
    tg_id: int,
    username: str | None,
    referrer_id: uuid.UUID | None,
    *,
    session: AsyncSession,
) -> User:
    """
    Создаёт пользователя (без профиля).

    Args:
        tg_id (int): Telegram ID.
        username (str | None): Telegram username.
        referrer_id (UUID | None): UUID реферера.
        session (AsyncSession): Сессия базы данных.

    Returns:
        User: Созданный пользователь.
    """
    is_admin = tg_id in settings.admin_id_list

    user = User(
        tg_id=tg_id,
        username=username,
        referrer_id=referrer_id,
        approval_status=(
            UserApprovalStatus.APPROVED if is_admin else UserApprovalStatus.PENDING
        ),
        approval_at=(datetime.now(timezone.utc) if is_admin else None),
        approved_by_admin_id=(tg_id if is_admin else None),
    )

    session.add(user)
    logger.info("Создан пользователь tg_id=%s", tg_id)
    await session.commit()
    return user


@connection()
async def update_user_profile(
    user_id: uuid.UUID,
    *,
    full_name: str,
    phone: str,
    city_id: uuid.UUID,
    gender: str,
    session: AsyncSession,
) -> None:
    """
    Обновляет профиль пользователя.

    Args:
        user_id (UUID): UUID пользователя.
        full_name (str): ФИО.
        phone (str): Телефон.
        city_id (UUID): UUID города.
        gender (str): Пол.
        session (AsyncSession): Сессия базы данных.
    """
    user = await session.get(User, user_id)
    if not user:
        return

    is_admin = user.tg_id in settings.admin_id_list

    values = {
        "full_name": full_name,
        "phone": phone,
        "city_id": city_id,
        "gender": gender,
    }

    if not is_admin:
        values["approval_status"] = UserApprovalStatus.PENDING

    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(**values)
    )

    logger.info(
        "Профиль пользователя %s обновлён (admin=%s)",
        user_id,
        is_admin,
    )

    await session.commit()


@connection()
async def get_profile_data(
    tg_id: int,
    *,
    session: AsyncSession,
) -> dict:
    """
    Возвращает данные профиля пользователя.

    Args:
        tg_id (int): Telegram ID пользователя.
        session (AsyncSession): Сессия базы данных.

    Returns:
        dict: Данные профиля.
    """
    user_stmt = select(User).where(User.tg_id == tg_id).options(selectinload(User.city))
    user = (await session.execute(user_stmt)).scalar_one()

    referrals_stmt = (
        select(func.count()).select_from(User).where(User.referrer_id == user.id)
    )
    referrals_count = await session.scalar(referrals_stmt) or 0

    approved_tasks_stmt = (
        select(func.count())
        .select_from(TaskAssignment)
        .where(
            TaskAssignment.user_id == user.id,
            TaskAssignment.status == TaskAssignmentStatus.APPROVED,
        )
    )
    orders_count = await session.scalar(approved_tasks_stmt) or 0

    return {
        "full_name": user.full_name or "—",
        "city": user.city.name if user.city else "—",
        "orders_count": orders_count,
        "referrals_count": referrals_count,
        "referral_link": f"https://t.me/MapSuccessBot?start=ref_{user.tg_id}",
    }


@connection()
async def get_approved_tasks(
    user_id: uuid.UUID,
    *,
    session,
) -> list[dict]:
    stmt = (
        select(Task.text, Task.link, Task.example_text)
        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.status == "APPROVED",
        )
        .order_by(TaskAssignment.processed_at.desc())
    )

    result = await session.execute(stmt)

    return [
        {"title": title, "link": link, "example_text": example_text}
        for title, link, example_text in result.all()
    ]


@connection()
async def get_referrals_with_stats(
    referrer_id: uuid.UUID,
    *,
    session,
) -> list[dict]:
    """
    Возвращает список подтверждённых рефералов
    + количество принятых (APPROVED) заданий.
    """

    ta = aliased(TaskAssignment)

    stmt = (
        select(
            User,
            func.count(ta.id).label("approved_count"),
        )
        .outerjoin(
            ta,
            (ta.user_id == User.id)
            & (ta.status == TaskAssignmentStatus.APPROVED)
            & (ta.is_archived == False),
        )
        .where(
            User.referrer_id == referrer_id,
            User.approval_status == UserApprovalStatus.APPROVED,
        )
        .options(
            selectinload(User.city),
        )
        .group_by(User.id)
        .order_by(User.approval_at)
    )

    rows = (await session.execute(stmt)).all()

    result: list[dict] = []

    for user, approved_count in rows:
        result.append(
            {
                "full_name": user.full_name or "—",
                "username": f"@{user.username}" if user.username else "—",
                "tg_id": user.tg_id,
                "city": user.city.name if user.city else "—",
                "approved_tasks": approved_count or 0,
            }
        )

    return result


@connection()
async def approve_user(*, session, tg_id: int, admin_tg_id: int) -> bool:
    stmt = (
        update(User)
        .where(User.tg_id == tg_id, User.approval_status == UserApprovalStatus.PENDING)
        .values(
            approval_status=UserApprovalStatus.APPROVED,
            approval_at=datetime.now(timezone.utc),
            approved_by_admin_id=admin_tg_id,
        )
        .returning(User.tg_id)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.scalar_one_or_none() is not None


@connection()
async def reject_user(*, session, tg_id: int, admin_tg_id: int) -> bool:
    stmt = (
        update(User)
        .where(User.tg_id == tg_id, User.approval_status == UserApprovalStatus.PENDING)
        .values(
            approval_status=UserApprovalStatus.REJECTED,
            approval_at=datetime.now(timezone.utc),
            approved_by_admin_id=admin_tg_id,
        )
        .returning(User.tg_id)
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.scalar_one_or_none() is not None


@connection()
async def save_approval_admin_message(
    *,
    session,
    user_id,
    admin_tg_id: int,
    message_id: int,
):
    session.add(
        UserApprovalAdminMessage(
            user_id=user_id,
            admin_tg_id=admin_tg_id,
            message_id=message_id,
        )
    )
    await session.commit()


@connection()
async def get_approval_messages_by_user(
    *,
    session,
    user_id,
):
    stmt = select(UserApprovalAdminMessage).where(
        UserApprovalAdminMessage.user_id == user_id
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@connection()
async def get_user_tg_id(
    *,
    session,
    user_id,
) -> int | None:
    result = await session.execute(select(User.tg_id).where(User.id == user_id))
    return result.scalar_one_or_none()
