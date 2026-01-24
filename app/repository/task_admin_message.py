import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import connection
from app.models.task_assigment_admin_message import (
    TaskAssignmentAdminMessage,
)


@connection()
async def save_admin_message(
    *,
    assignment_id: uuid.UUID,
    admin_tg_id: int,
    message_id: int,
    session: AsyncSession,
) -> None:
    session.add(
        TaskAssignmentAdminMessage(
            assignment_id=assignment_id,
            admin_tg_id=admin_tg_id,
            message_id=message_id,
        )
    )
    await session.commit()


@connection()
async def get_admin_messages_by_assignment(
    *,
    assignment_id: uuid.UUID,
    session: AsyncSession,
) -> list[TaskAssignmentAdminMessage]:
    res = await session.execute(
        select(TaskAssignmentAdminMessage).where(
            TaskAssignmentAdminMessage.assignment_id == assignment_id
        )
    )
    return res.scalars().all()


@connection()
async def delete_admin_messages_by_assignment(
    *,
    assignment_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    res = await session.execute(
        select(TaskAssignmentAdminMessage).where(
            TaskAssignmentAdminMessage.assignment_id == assignment_id
        )
    )
    for row in res.scalars():
        await session.delete(row)

    await session.commit()
