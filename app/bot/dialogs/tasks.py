from __future__ import annotations

import logging

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery

from aiogram_dialog import (
    Dialog,
    Window,
    DialogManager,
    StartMode,
)
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.input import TextInput, MessageInput

from app.bot.dialogs.states import TasksSG, MainMenuSG
from app.bot.utils.tg import notify_admins_about_report
from app.repository.task import (
    get_active_assignment,
    assign_random_task,
    submit_report,
    save_assignment_report_message_id,
)
from app.repository.user import get_user_by_tg_id

logger = logging.getLogger(__name__)


async def tasks_getter(dialog_manager: DialogManager, **_) -> dict:
    tg_id = dialog_manager.event.from_user.id
    user = await get_user_by_tg_id(tg_id)

    assignment = await get_active_assignment(user.id)

    if not assignment:
        return {
            "state": "empty",
            "title": "📦 Задания",
            "text": "У вас нет активных заданий.",
        }

    task = assignment.task

    example_block = (
        f"\n\n✍️ <b>Пример:</b>\n{task.example_text}" if task.example_text else ""
    )

    base_text = f"{task.text}{example_block}\n\n🔗 <b>Ссылка:</b>\n{task.link}"

    if assignment.status == "ASSIGNED":
        return {
            "state": "assigned",
            "assignment_id": assignment.id,
            "title": "📦 Текущее задание",
            "text": base_text,
        }

    if assignment.status == "SUBMITTED":
        return {
            "state": "checking",
            "assignment_id": assignment.id,
            "title": "📦 Задание на проверке",
            "text": (
                base_text
                + "\n\n⏳ <i>Отчёт отправлен и ожидает проверки администратора</i>"
            ),
        }

    return {
        "state": "empty",
        "title": "📦 Задания",
        "text": "У вас нет активных заданий.",
    }



async def resolve_tasks_state(dialog_manager: DialogManager):
    data = await tasks_getter(dialog_manager)
    state = data["state"]

    if state == "assigned":
        await dialog_manager.switch_to(TasksSG.assigned)
    elif state == "checking":
        await dialog_manager.switch_to(TasksSG.checking)
    else:
        await dialog_manager.switch_to(TasksSG.empty)



async def on_start(start_data, dialog_manager: DialogManager):
    dialog_manager.dialog_data.clear()
    await resolve_tasks_state(dialog_manager)


async def get_task(
    callback: CallbackQuery,
    button: Button,
    dialog_manager: DialogManager,
):
    user = await get_user_by_tg_id(callback.from_user.id)
    assignment = await assign_random_task(user)

    if not assignment:
        await callback.answer(
            "⏳ У вас уже есть задание (выполняется или на проверке).",
            show_alert=True,
        )
        return

    await resolve_tasks_state(dialog_manager)


async def start_report(
    callback: CallbackQuery,
    button: Button,
    dialog_manager: DialogManager,
):
    data = await tasks_getter(dialog_manager)
    dialog_manager.dialog_data["assignment_id"] = data["assignment_id"]
    await dialog_manager.switch_to(TasksSG.report_account)


async def save_account(
    message: Message,
    widget: TextInput,
    dialog_manager: DialogManager,
    value: str,
):
    account = value.strip()

    if not account:
        await message.answer("❗ Укажите имя аккаунта.")
        return

    if len(account) > 128:
        await message.answer("❗ Максимум 128 символов.")
        return

    dialog_manager.dialog_data["account_name"] = account
    await dialog_manager.switch_to(TasksSG.report_photo)


async def invalid_photo(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
):
    await message.answer(
        "❗ Пожалуйста, отправьте <b>фото</b>.",
        parse_mode=ParseMode.HTML,
    )


async def save_photo(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
):
    payload = await submit_report(
        assignment_id=dialog_manager.dialog_data["assignment_id"],
        account_name=dialog_manager.dialog_data["account_name"],
        photo_file_id=message.photo[-1].file_id,
    )

    await notify_admins_about_report(message.bot, payload)

    await dialog_manager.start(
        TasksSG.checking,
        mode=StartMode.RESET_STACK,
    )

    dialog_msg = dialog_manager.middleware_data.get("message")
    if dialog_msg:
        await save_assignment_report_message_id(
            assignment_id=payload["assignment"]["id"],
            message_id=dialog_msg.message_id,
        )


async def back_to_menu(
    callback: CallbackQuery,
    button: Button,
    dialog_manager: DialogManager,
):
    await dialog_manager.start(
        MainMenuSG.main,
        mode=StartMode.RESET_STACK,
    )


tasks_dialog = Dialog(
    Window(
        Format("<b>{title}</b>\n\n{text}"),
        Button(
            Const("📦 Получить задание"),
            id="get",
            on_click=get_task,
            when=lambda d, *_: d["state"] == "empty",
        ),
        Button(
            Const("📤 Отправить отчёт"),
            id="report",
            on_click=start_report,
            when=lambda d, *_: d["state"] == "assigned",
        ),
        Button(
            Const("⬅️ В меню"),
            id="menu",
            on_click=back_to_menu,
        ),
        getter=tasks_getter,
        state=TasksSG.empty,
        disable_web_page_preview=True,
    ),
    Window(
        Format("<b>{title}</b>\n\n{text}"),
        Button(
            Const("📤 Отправить отчёт"),
            id="report",
            on_click=start_report,
        ),
        Button(
            Const("⬅️ В меню"),
            id="menu",
            on_click=back_to_menu,
        ),
        getter=tasks_getter,
        state=TasksSG.assigned,
        disable_web_page_preview=True,
    ),
    Window(
        Format("<b>{title}</b>\n\n{text}"),
        Button(
            Const("⬅️ В меню"),
            id="menu",
            on_click=back_to_menu,
        ),
        getter=tasks_getter,
        state=TasksSG.checking,
        disable_web_page_preview=True,
    ),
    Window(
        Const("✍️ Укажите имя аккаунта:"),
        TextInput(id="account", on_success=save_account),
        Button(Const("⬅️ В меню"), id="menu", on_click=back_to_menu),
        state=TasksSG.report_account,
    ),
    Window(
        Const("📸 Отправьте фото-подтверждение:"),
        MessageInput(func=save_photo, filter=F.photo),
        MessageInput(func=invalid_photo),
        state=TasksSG.report_photo,
        disable_web_page_preview=True,
    ),
    on_start=on_start,
)
