import uuid
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, func, exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
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

MSC_TZ = timezone(timedelta(hours=3))


def _ekb_day_start() -> datetime:
    now = datetime.now(MSC_TZ)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


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
async def get_current_assignment(
    user_id: uuid.UUID,
    *,
    session,
) -> TaskAssignment | None:
    stmt = (
        select(TaskAssignment)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.is_archived.is_(False),
            TaskAssignment.status == TaskAssignmentStatus.ASSIGNED,
        )
        .options(selectinload(TaskAssignment.task))
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()


@connection()
async def get_submitted_count(
    user_id: uuid.UUID,
    *,
    session,
) -> int:
    stmt = (
        select(func.count())
        .select_from(TaskAssignment)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.is_archived.is_(False),
            TaskAssignment.status == TaskAssignmentStatus.SUBMITTED,
        )
    )
    res = await session.execute(stmt)
    return res.scalar_one()


@connection()
async def has_available_tasks_for_source(
    user,
    *,
    session,
    source: str,
) -> bool:
    """
    Проверяем, есть ли хоть одно доступное задание по source
    (НЕ создаём assignment, пол не учитываем).
    Учитываем:
      - город (Task.city_id is None или совпадает с user.city_id)
      - не занятость (нет активного неархивного TaskAssignment)
      - source совпадает
    """
    stmt = (
        select(Task.id)
        .where(
            Task.source == source,
            or_(Task.city_id.is_(None), Task.city_id == user.city_id),
            ~Task.id.in_(
                select(TaskAssignment.task_id).where(
                    TaskAssignment.is_archived.is_(False),
                )
            ),
        )
        .limit(1)
    )

    task_id = (await session.execute(stmt)).scalar_one_or_none()
    return task_id is not None


@connection()
async def assign_random_task(
    user: User,
    *,
    session,
    source: str | None,
    required_gender: str | None,
) -> TaskAssignment | str | None:
    logger.info(f"[ASSIGN_START] tg_id={user.tg_id}")

    if user.is_blocked:
        return "blocked"

    current = await get_current_assignment(user.id)
    if current:
        logger.info(f"[ASSIGN_HAS_ACTIVE] tg_id={user.tg_id}")
        return "has_active"

    submitted_count = await get_submitted_count(user.id)
    if submitted_count >= settings.max_active_assignments:
        logger.info(
            f"[ASSIGN_SUBMITTED_LIMIT] tg_id={user.tg_id} submitted={submitted_count}"
        )
        return "submitted_limit"

    conditions = [
        or_(Task.city_id.is_(None), Task.city_id == user.city_id),
        Task.source == source,
        ~Task.id.in_(
            select(TaskAssignment.task_id).where(
                TaskAssignment.is_archived.is_(False),
            )
        ),
        ~Task.id.in_(
            select(TaskAssignment.task_id).where(
                TaskAssignment.user_id == user.id,
            )
        ),
    ]

    if required_gender is not None:
        conditions.append(
            or_(
                Task.required_gender.is_(None),
                Task.required_gender == required_gender,
            )
        )

    stmt = select(Task).where(*conditions).order_by(func.random()).limit(1)

    task = (await session.execute(stmt)).scalars().first()

    if not task:
        return "no_tasks"

    assignment = TaskAssignment(
        user_id=user.id,
        task_id=task.id,
        status=TaskAssignmentStatus.ASSIGNED,
    )
    session.add(assignment)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return "no_tasks"

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
        raise ValueError("Нельзя отправить отчёт для задания в текущем статусе")

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


@connection()
async def archive_assignment_by_id(*, assignment_id: int, session) -> bool:
    stmt = (
        update(TaskAssignment)
        .where(
            TaskAssignment.status == TaskAssignmentStatus.REJECTED,
            TaskAssignment.id == assignment_id,
            TaskAssignment.is_archived.is_(False),
        )
        .values(is_archived=True)
        .returning(TaskAssignment.id)
    )

    result = await session.execute(stmt)
    await session.commit()

    return result.scalar() is not None


@connection()
async def get_avg_execution_time(*, session: AsyncSession) -> float:
    """
    Возвращает среднее время выполнения задания (в минутах).
    Считаем только APPROVED и REJECTED, у которых есть submitted_at.
    """

    stmt = select(
        func.avg(
            func.extract(
                "epoch", TaskAssignment.submitted_at - TaskAssignment.created_at
            )
        )
    ).where(
        TaskAssignment.status.in_(
            [
                TaskAssignmentStatus.APPROVED,
                TaskAssignmentStatus.REJECTED,
            ]
        ),
        TaskAssignment.submitted_at.is_not(None),
    )

    avg_seconds = await session.scalar(stmt)

    if not avg_seconds:
        return 0.0

    return avg_seconds / 60


@connection()
async def get_tasks_statistics(*, session: AsyncSession) -> dict:
    total_tasks = await session.scalar(select(func.count(Task.id)))

    total_assignments = await session.scalar(select(func.count(TaskAssignment.id)))

    avg_execution_minutes = await get_avg_execution_time()

    approved = await session.scalar(
        select(func.count(TaskAssignment.id)).where(
            TaskAssignment.status == TaskAssignmentStatus.APPROVED
        )
    )

    in_progress = await session.scalar(
        select(func.count(TaskAssignment.id)).where(
            TaskAssignment.status.in_(
                [
                    TaskAssignmentStatus.ASSIGNED,
                    TaskAssignmentStatus.SUBMITTED,
                ]
            )
        )
    )

    rejected = await session.scalar(
        select(func.count(TaskAssignment.id)).where(
            TaskAssignment.status == TaskAssignmentStatus.REJECTED
        )
    )

    free_tasks = await session.scalar(
        select(func.count(Task.id)).where(
            ~exists().where(
                TaskAssignment.task_id == Task.id,
                TaskAssignment.is_archived.is_(False),
            )
        )
    )

    approved_users = await session.scalar(
        select(func.count(func.distinct(TaskAssignment.user_id))).where(
            TaskAssignment.status == TaskAssignmentStatus.APPROVED
        )
    )

    return {
        "total_tasks": total_tasks or 0,
        "total_assignments": total_assignments or 0,
        "approved": approved or 0,
        "in_progress": in_progress or 0,
        "rejected": rejected or 0,
        "free_tasks": free_tasks or 0,
        "approved_users": approved_users or 0,
        "avg_execution_minutes": round(avg_execution_minutes, 2),
    }


@connection()
async def get_submitted_assignments(
    user_id: uuid.UUID,
    *,
    session,
) -> list[TaskAssignment]:
    stmt = (
        select(TaskAssignment)
        .where(
            TaskAssignment.user_id == user_id,
            TaskAssignment.is_archived.is_(False),
            TaskAssignment.status == TaskAssignmentStatus.SUBMITTED,
        )
        .options(
            selectinload(TaskAssignment.task),
            selectinload(TaskAssignment.user),
            selectinload(TaskAssignment.reports),
        )
        .order_by(TaskAssignment.submitted_at.desc())
    )
    res = await session.execute(stmt)
    return res.scalars().all()
