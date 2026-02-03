from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram_dialog import DialogManager

from app.core.settings import settings
from app.repository.user import get_user_by_tg_id

logger = logging.getLogger(__name__)


class RegistrationMiddleware(BaseMiddleware):
    """
    Middleware, запрещающая доступ к функционалу бота
    пользователям, не прошедшим регистрацию.
    """

    async def __call__(self, handler, event, data):
        """
        Проверяет регистрацию пользователя перед выполнением обработчика.

        Args:
            handler: Обработчик события.
            event (Message | CallbackQuery): Событие Telegram.
            data (dict): Контекст события.
        """
        if isinstance(event, (Message, CallbackQuery)):
            tg_id = event.from_user.id
        else:
            return await handler(event, data)

        if tg_id in settings.admin_id_list:
            return await handler(event, data)
        if (
            isinstance(event, Message)
            and event.text
            and event.text.startswith("/start")
        ):
            return await handler(event, data)

        dialog_manager: DialogManager | None = data.get("dialog_manager")
        if dialog_manager and dialog_manager.has_active_dialog():
            return await handler(event, data)

        user = await get_user_by_tg_id(tg_id)

        if not user or not user.full_name:
            logger.info(
                "Пользователь %s заблокирован middleware (не зарегистрирован)",
                tg_id,
            )

            if isinstance(event, Message):
                await event.answer(
                    "❗ Для работы с ботом необходимо пройти регистрацию.\n"
                    "Нажмите /start"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "Необходимо пройти регистрацию через /start",
                    show_alert=True,
                )
            return

        return await handler(event, data)
