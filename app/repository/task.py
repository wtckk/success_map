import random
import uuid
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import connection
from app.models import TaskReport
from app.models.task_assignment import (
    TaskAssignment,
    TaskAssignmentStatus,
)

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.models.task import Task
from app.models.user import User

logger = logging.getLogger(__name__)


@connection()
async def get_active_assignment(
    user_id: uuid.UUID,
    *,
    session,
) -> TaskAssignment | None:
    stmt = (
        select(TaskAssignment)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.is_archived.is_(False),
            TaskAssignment.status.in_(
                [
                    TaskAssignmentStatus.ASSIGNED,
                    TaskAssignmentStatus.SUBMITTED,
                ]
            ),
        )
        .options(selectinload(TaskAssignment.task))
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


@connection()
async def assign_random_task(
    user: User,
    *,
    session,
) -> TaskAssignment | None | str:
    logger.info(
        "Попытка выдачи задания пользователю tg_id=%s user_id=%s",
        user.tg_id,
        user.id,
    )

    if user.is_blocked:
        logger.warning(
            "Пользователь заблокирован, задание не выдано tg_id=%s",
            user.tg_id,
        )
        return "blocked"

    active = await get_active_assignment(user.id)
    if active:
        logger.info(
            "У пользователя уже есть активное задание assignment_id=%s tg_id=%s",
            active.id,
            user.tg_id,
        )
        return "already_has"

    # подходящие задания
    stmt = select(Task).where(
        or_(Task.city_id.is_(None), Task.city_id == user.city_id),
        ~Task.id.in_(
            select(TaskAssignment.task_id).where(
                TaskAssignment.is_archived.is_(False),
            )
        ),
    )

    tasks = (await session.execute(stmt)).scalars().all()
    if not tasks:
        logger.info(
            "Нет доступных заданий для пользователя tg_id=%s city_id=%s",
            user.tg_id,
            user.city_id,
        )
        return "no_tasks"

    task = random.choice(tasks)

    assignment = TaskAssignment(
        user_id=user.id,
        task_id=task.id,
        status=TaskAssignmentStatus.ASSIGNED,
    )
    session.add(assignment)
    await session.commit()

    logger.info(
        "Задание выдано assignment_id=%s task_id=%s tg_id=%s",
        assignment.id,
        task.id,
        user.tg_id,
    )

    return assignment


@connection()
async def submit_report(
    assignment_id: uuid.UUID,
    account_name: str,
    photo_file_id: str,
    session: AsyncSession,
) -> dict:
    """
    Сохраняет отчёт по заданию и переводит выдачу задания в статус SUBMITTED.
    Возвращает данные для уведомления администраторов.

    Args:
        assignment_id (UUID): ID выданного задания (task_assignments.id).
        account_name (str): Имя аккаунта, на который выполнено задание.
        photo_file_id (str): Telegram file_id фотографии.
        session: Сессия БД
    Returns:
        dict: Данные для уведомления администраторов (user/task/city/report).
    """
    result = await session.execute(
        select(TaskAssignment)
        .where(TaskAssignment.id == assignment_id)
        .options(
            selectinload(TaskAssignment.user).selectinload(User.city),
            selectinload(TaskAssignment.task).selectinload(Task.city),
        )
    )
    assignment: TaskAssignment | None = result.scalar_one_or_none()

    if not assignment:
        raise ValueError("TaskAssignment не найден")

    if assignment.user.is_blocked:
        raise ValueError("Пользователь заблокирован и не может отправлять отчёты")
    if assignment.status != TaskAssignmentStatus.ASSIGNED:
        # Если отчёт уже отправлен/принят/отклонён — не перезаписываем
        raise ValueError("Нельзя отправить отчёт для задания в текущем статусе")

    # 1) создаём/заменяем отчёт (у тебя unique=True на assignment_id)
    existing_report = await session.execute(
        select(TaskReport).where(TaskReport.assignment_id == assignment_id)
    )
    report = existing_report.scalar_one_or_none()

    if report:
        report.account_name = account_name
        report.photo_file_id = photo_file_id
    else:
        report = TaskReport(
            assignment_id=assignment_id,
            account_name=account_name,
            photo_file_id=photo_file_id,
        )
        session.add(report)

    # 2) обновляем статус выдачи
    assignment.status = TaskAssignmentStatus.SUBMITTED
    assignment.submitted_at = datetime.now(timezone.utc)

    await session.commit()

    user = assignment.user
    task = assignment.task
    city = task.city if task else None

    logger.info(
        "Отчёт сохранён assignment_id=%s tg_id=%s",
        assignment_id,
        user.tg_id,
    )
    return {
        "assignment": {
            "id": assignment.id,
            "status": assignment.status,
            "submitted_at": assignment.submitted_at,
        },
        "user": {
            "id": user.id,
            "tg_id": user.tg_id,
            "username": user.username,
            "full_name": user.full_name,
        },
        "task": {
            "id": task.id,
            "text": task.text,
            "example_text": task.example_text,
            "link": task.link,
            "required_gender": task.required_gender,
        },
        "city": (
            {
                "id": city.id,
                "name": city.name,
            }
            if city
            else None
        ),
        "report": {
            "account_name": report.account_name,
            "photo_file_id": report.photo_file_id,
        },
    }


@connection()
async def process_assignment(
    assignment_id: uuid.UUID,
    action: str,
    admin_tg_id: int,
    *,
    session,
) -> TaskAssignment | None:
    assignment = await session.get(TaskAssignment, assignment_id)

    if not assignment:
        return None

    if assignment.status != TaskAssignmentStatus.SUBMITTED:
        # уже обработано
        return assignment

    if action == "approve":
        assignment.status = TaskAssignmentStatus.APPROVED
    elif action == "reject":
        assignment.status = TaskAssignmentStatus.REJECTED
    else:
        raise ValueError("Неизвестное действие администратора")

    assignment.processed_by_admin_id = admin_tg_id
    assignment.processed_at = datetime.now(timezone.utc)

    logger.info(
        "Задание %s обработано админом %s: %s",
        assignment.id,
        admin_tg_id,
        assignment.status,
    )
    await session.commit()
    return assignment


@connection()
async def review_assignment(
    *,
    session: AsyncSession,
    assignment_id,
    admin_tg_id: int,
    approve: bool,
) -> TaskAssignment | None:
    stmt = (
        select(TaskAssignment)
        .where(
            TaskAssignment.id == assignment_id,
            TaskAssignment.status == TaskAssignmentStatus.SUBMITTED,
        )
        .options(
            selectinload(TaskAssignment.user),
            selectinload(TaskAssignment.task),
        )
        .with_for_update()
    )

    res = await session.execute(stmt)
    assignment = res.scalar_one_or_none()

    if not assignment:
        return None

    if assignment.status != TaskAssignmentStatus.SUBMITTED:
        return assignment  # уже обработан

    assignment.status = (
        TaskAssignmentStatus.APPROVED if approve else TaskAssignmentStatus.REJECTED
    )
    assignment.processed_by_admin_id = admin_tg_id
    assignment.processed_at = datetime.now(timezone.utc)

    await session.commit()
    logger.info(
        "Задание %s проверено админом %s: %s",
        assignment.id,
        admin_tg_id,
        assignment.status,
    )

    return assignment


@connection()
async def save_assignment_report_message_id(
    *,
    session: AsyncSession,
    assignment_id: uuid.UUID,
    message_id: int,
):
    assignment = await session.get(TaskAssignment, assignment_id)
    if assignment:
        assignment.report_message_id = message_id
        await session.commit()


MSC_TZ = timezone(timedelta(hours=3))


def _ekb_day_start() -> datetime:
    now = datetime.now(MSC_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


@connection()
async def archive_rejected_assignments(*, session) -> int:
    """
    Архивирует REJECTED задания прошлых дней,
    чтобы они не мешали повторной выдаче.
    """
    today_start = _ekb_day_start()

    stmt = (
        update(TaskAssignment)
        .where(
            TaskAssignment.status == TaskAssignmentStatus.REJECTED,
            TaskAssignment.is_archived.is_(False),
            TaskAssignment.processed_at < today_start,
        )
        .values(is_archived=True)
    )

    result = await session.execute(stmt)
    await session.commit()

    count = result.rowcount or 0
    logger.info("Archived rejected assignments: %s", count)
    return count
