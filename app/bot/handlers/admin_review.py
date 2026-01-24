from aiogram import Router, Bot
from aiogram.types import CallbackQuery
from aiogram.enums import ParseMode

import logging


from app.bot.callbacks.admin import AdminReviewCB

from app.bot.utils.tg import notify_user_about_review
from app.repository.task import review_assignment
from app.repository.task_admin_message import (
    get_admin_messages_by_assignment,
    delete_admin_messages_by_assignment,
)

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(AdminReviewCB.filter())
async def admin_review_handler(
    callback: CallbackQuery,
    callback_data: AdminReviewCB,
    bot: Bot,
):
    approve = callback_data.action == "approve"

    assignment = await review_assignment(
        assignment_id=callback_data.assignment_id,
        admin_tg_id=callback.from_user.id,
        approve=approve,
    )

    if not assignment:
        await callback.answer("⚠️ Задание не найдено", show_alert=True)
        return

    if assignment.processed_by_admin_id != callback.from_user.id:
        await callback.answer(
            "⚠️ Задание уже обработано другим администратором",
            show_alert=True,
        )
        return

    if assignment.report_message_id:
        try:
            await bot.delete_message(
                chat_id=assignment.user.tg_id,
                message_id=assignment.report_message_id,
            )
        except Exception:
            logger.warning(
                "Не удалось удалить сообщение отчёта tg_id=%s message_id=%s",
                assignment.user.tg_id,
                assignment.report_message_id,
            )

    status_text = "✅ <b>Одобрено</b>" if approve else "❌ <b>Отклонено</b>"

    new_caption = (
        callback.message.caption
        + "\n\n"
        + status_text
        + f"\n👨‍⚖️ Администратор: @{callback.from_user.username or callback.from_user.id}"
    )

    messages = await get_admin_messages_by_assignment(assignment_id=assignment.id)

    for msg in messages:
        try:
            await bot.edit_message_caption(
                chat_id=msg.admin_tg_id,
                message_id=msg.message_id,
                caption=new_caption,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    await delete_admin_messages_by_assignment(assignment_id=assignment.id)

    await notify_user_about_review(
        bot=bot,
        tg_id=assignment.user.tg_id,
        approved=approve,
        task_text=assignment.task.text,
    )

    await callback.answer("Готово")
