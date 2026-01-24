from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Any, Awaitable, Callable, Dict


from app.core.settings import settings
from app.repository.user import is_user_blocked

BLOCKED_TEXT = "🚫 <b>Вы заблокированы</b>\n\nДоступ к функциям бота ограничен.\n"


class BlockUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        tg_id: int | None = None

        if isinstance(event, (Message, CallbackQuery)):
            tg_id = event.from_user.id

        if not tg_id:
            return await handler(event, data)

        if tg_id in settings.admin_id_list:
            return await handler(event, data)

        if await is_user_blocked(tg_id=tg_id):
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Вы заблокированы", show_alert=True)
            else:
                await event.answer(BLOCKED_TEXT)

            return

        return await handler(event, data)
