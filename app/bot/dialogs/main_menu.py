from __future__ import annotations

import logging

from aiogram.types import CallbackQuery

from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Column, Row
from aiogram_dialog.widgets.text import Const

from app.bot.dialogs.admin import go_to_admin_panel
from app.bot.dialogs.states import (
    MainMenuSG,
    ProfileSG,
    TasksSG,
    PaymentsSG,
    RulesSG,
    ContactsSG,
)
from app.core.settings import settings

logger = logging.getLogger(__name__)


def is_admin(data: dict, widget, manager: DialogManager) -> bool:
    user = manager.event.from_user
    return user.id in settings.admin_id_list


async def go_profile(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Открывает экран профиля.

    Args:
        callback (CallbackQuery): Callback от Telegram.
        widget (Button): Нажатая кнопка.
        dialog_manager (DialogManager): Менеджер диалога.
    """
    await dialog_manager.start(ProfileSG.main, mode=StartMode.RESET_STACK)


async def go_tasks(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Открывает экран заданий.

    Args:
        callback (CallbackQuery): Callback от Telegram.
        widget (Button): Нажатая кнопка.
        dialog_manager (DialogManager): Менеджер диалога.
    """
    await dialog_manager.start(TasksSG.empty, mode=StartMode.RESET_STACK)


async def go_payments(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Открывает экран выплат.

    Args:
        callback (CallbackQuery): Callback от Telegram.
        widget (Button): Нажатая кнопка.
        dialog_manager (DialogManager): Менеджер диалога.
    """
    await dialog_manager.start(PaymentsSG.main, mode=StartMode.RESET_STACK)


async def go_rules(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Открывает экран правил.

    Args:
        callback (CallbackQuery): Callback от Telegram.
        widget (Button): Нажатая кнопка.
        dialog_manager (DialogManager): Менеджер диалога.
    """
    await dialog_manager.start(RulesSG.main, mode=StartMode.RESET_STACK)


async def go_contacts(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Открывает экран контактов.

    Args:
        callback (CallbackQuery): Callback от Telegram.
        widget (Button): Нажатая кнопка.
        dialog_manager (DialogManager): Менеджер диалога.
    """
    await dialog_manager.start(ContactsSG.main, mode=StartMode.RESET_STACK)


main_menu_dialog = Dialog(
    Window(
        Const("🧭 <b>Главное меню</b>\n\nВыберите нужный раздел:"),
        Row(
            Button(
                Const("📦 Задания"),
                id="tasks",
                on_click=go_tasks,
            ),
        ),
        Row(
            Button(
                Const("👤 Профиль"),
                id="profile",
                on_click=go_profile,
            ),
            Button(
                Const("💰 Выплаты"),
                id="payments",
                on_click=go_payments,
            ),
        ),
        Row(
            Button(
                Const("📜 Правила"),
                id="rules",
                on_click=go_rules,
            ),
            Button(
                Const("☎️ Контакты"),
                id="contacts",
                on_click=go_contacts,
            ),
        ),
        Column(
            Button(
                Const("🛠 Админ-панель"),
                id="admin",
                on_click=go_to_admin_panel,
                when=is_admin,
            ),
        ),
        state=MainMenuSG.main,
    ),
)
