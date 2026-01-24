from aiogram import BaseMiddleware

from app.repository.user import get_user_by_tg_id
from app.models.user import UserApprovalStatus


class ApprovalMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        tg_id = None

        if event.message and event.message.from_user:
            tg_id = event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            tg_id = event.callback_query.from_user.id

        if not tg_id:
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
            return

        return await handler(event, data)
