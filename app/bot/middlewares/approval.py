import logging
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from app.core.settings import settings
from app.repository.user import get_user_by_tg_id
from app.models.user import UserApprovalStatus

logger = logging.getLogger(__name__)

class ApprovalMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        tg_id = None

        from aiogram.types import Message
        if isinstance(event, Message) and event.from_user:
            tg_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            tg_id = event.from_user.id

        if not tg_id:
            return await handler(event, data)

        if tg_id in settings.admin_id_list:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            cb_data = event.data or ""
            if cb_data.startswith("user_approve:") or cb_data.startswith("user_reject:"):
                logger.info(
                    "ApprovalMiddleware: bypass approval callback %s from tg_id=%s",
                    cb_data,
                    tg_id,
                )
                return await handler(event, data)
        if (
            event.message
            and event.message.text
            and event.message.text.startswith("/start")
        ):
            return await handler(event, data)

        user = await get_user_by_tg_id(tg_id=tg_id)
        if not user:
            return await handler(event, data)

        if not user.full_name:
            return await handler(event, data)

        if user.approval_status == UserApprovalStatus.PENDING:
            text = (
                "⏳ Ваша заявка на регистрацию находится на проверке.\n\n"
                "Обычно это занимает немного времени. Пожалуйста, подождите."
            )
            if event.callback_query:
                await event.callback_query.answer(text, show_alert=True)
            else:
                await event.message.answer(text)
                logger.info(
                    "ApprovalMiddleware blocked tg_id=%s (PENDING)",
                    tg_id,
                )
            return

        if user.approval_status == UserApprovalStatus.REJECTED:
            text = (
                "❌ В доступе отказано.\n\n"
                "К сожалению, вы не прошли проверку и не можете пользоваться ботом."
            )
            if event.callback_query:
                await event.callback_query.answer(text, show_alert=True)
            else:
                await event.message.answer(text)
                logger.info(
                    "ApprovalMiddleware blocked tg_id=%s (REJECTED)",
                    tg_id,
                )
            return

        return await handler(event, data)
