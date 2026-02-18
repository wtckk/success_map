import logging

from aiogram import F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.input import TextInput, MessageInput

from app.bot.dialogs.states import TasksSG, MainMenuSG
from app.bot.ui.widgets.custom_button import CustomEmojiButton
from app.bot.utils.tg import notify_admins_about_report
from app.core.settings import settings
from app.repository.task import (
    assign_random_task,
    has_available_tasks_for_source,
    submit_report,
    save_assignment_report_message_id,
    get_current_assignment,
    get_submitted_count,
    get_submitted_assignments,
)
from app.repository.user import get_user_by_tg_id

logger = logging.getLogger(__name__)

SOURCE_MAP = {
    "yandex": (
        "Яндекс Карты",
        "Яндекс Карты",
        "5359811897677848798",  # yandex
    ),
    "2gis": (
        "2ГИС",
        "2ГИС",
        "5244638999561135703",  # 2gis
    ),
    "google": (
        "Google Maps",
        "Google Maps",
        "5343611925282435092",  # google
    ),
}


# helpers
def user_ctx(user) -> str:
    return f"tg_id={user.tg_id} user_id={user.id}"


async def load_user(dialog_manager: DialogManager):
    tg_id = dialog_manager.event.from_user.id
    return await get_user_by_tg_id(tg_id)


# task flow
async def get_task(
    callback: CallbackQuery,
    button: Button,
    dialog_manager: DialogManager,
):
    user = await get_user_by_tg_id(callback.from_user.id)

    if user.is_blocked:
        logger.warning(f"BLOCKED_USER_ATTEMPT | tg_id={user.tg_id}")
        await callback.answer("⛔ Ваш аккаунт заблокирован.", show_alert=True)
        return

    current = await get_current_assignment(user.id)
    if current:
        logger.info(f"TASK_DENY_ACTIVE | {user_ctx(user)}")
        await callback.answer(
            "📤 Сначала отправьте отчёт по текущему заданию.",
            show_alert=True,
        )
        return

    submitted_count = await get_submitted_count(user.id)
    if submitted_count >= settings.max_active_assignments:
        logger.info(
            f"TASK_DENY_LIMIT | {user_ctx(user)} "
            f"limit={settings.max_active_assignments}"
        )
        await callback.answer(
            f"⛔ У вас уже {settings.max_active_assignments} "
            "заданий на проверке.\n"
            "Вы достигли лимита",
            show_alert=True,
        )
        return

    logger.info(f"TASK_OPEN_SOURCE_SELECTION | {user_ctx(user)}")

    dialog_manager.dialog_data.clear()
    await dialog_manager.switch_to(TasksSG.choose_source)


async def choose_source(
    callback: CallbackQuery, button: Button, dialog_manager: DialogManager
):
    user = await load_user(dialog_manager)

    source_key = button.widget_id
    source_title, source_value, _ = SOURCE_MAP[source_key]

    has_tasks = await has_available_tasks_for_source(user, source=source_value)
    if not has_tasks:
        logger.info(f"TASK_DENY_NO_SOURCE | {user_ctx(user)} source='{source_value}'")
        await callback.answer(
            f"📭 Сейчас нет доступных заданий из источника {source_title}.",
            show_alert=True,
        )
        return

    dialog_manager.dialog_data["source"] = source_key
    await dialog_manager.switch_to(TasksSG.choose_gender)


async def choose_gender(
    callback: CallbackQuery, button: Button, dialog_manager: DialogManager
):
    user = await load_user(dialog_manager)

    source_key = dialog_manager.dialog_data["source"]
    source_value = SOURCE_MAP[source_key][1]

    gender = {"male": "M", "female": "F", "any": None}[button.widget_id]

    logger.info(
        f"TASK_REQUEST | {user_ctx(user)} source='{source_value}' gender='{gender}'"
    )

    result = await assign_random_task(
        user,
        source=source_value,
        required_gender=gender,
    )

    if result == "blocked":
        logger.warning(f"TASK_DENY_BLOCKED | {user_ctx(user)}")
        await callback.answer("⛔ Ваш аккаунт заблокирован.", show_alert=True)
        return

    if result == "has_active":
        logger.info(f"TASK_DENY_ACTIVE | {user_ctx(user)}")
        await callback.answer(
            "📤 Сначала отправьте отчёт по текущему заданию.",
            show_alert=True,
        )
        return

    if result == "submitted_limit":
        logger.info(
            f"TASK_DENY_LIMIT | {user_ctx(user)} "
            f"limit={settings.max_active_assignments}"
        )
        await callback.answer(
            f"⛔ У вас уже {settings.max_active_assignments} заданий на проверке.",
            show_alert=True,
        )
        return

    if result == "no_tasks":
        logger.info(f"TASK_DENY_NO_TASKS | {user_ctx(user)}")
        await callback.answer("📭 Нет доступных заданий.", show_alert=True)
        return

    logger.info(
        f"TASK_ASSIGNED | {user_ctx(user)} "
        f"assignment_id={result.id} task_id={result.task_id}"
    )

    await dialog_manager.start(TasksSG.empty, mode=StartMode.RESET_STACK)


# getter
async def review_list_getter(dialog_manager: DialogManager, **_):
    user = await load_user(dialog_manager)
    assignments = await get_submitted_assignments(user.id)

    if not assignments:
        return {"text": "Нет заданий в обработке."}

    blocks = []

    source_prefix = {
        "Яндекс Карты": "Яндекс Карты",
        "Google Maps": "Google Maps",
        "2ГИС": "2ГИС",
    }

    for a in assignments:
        task = a.task
        report = a.reports[0] if a.reports else None

        account_name = report.account_name if report else "Не указано"

        prefix = source_prefix.get(task.source, "MAP")

        blocks.append(
            f"🆔 <b>{prefix}</b>\n"
            f"🌐 Источник: {task.source}\n"
            f"👤 Аккаунт: <b>{account_name}</b>\n"
            f"📝 {task.example_text}\n"
            f"📅 Отправлено: {a.submitted_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"🔗 <a href='{task.link}'>Перейти</a>\n"
        )

    return {"text": "\n\n".join(blocks)}


async def tasks_getter(dialog_manager: DialogManager, **_) -> dict:
    user = await load_user(dialog_manager)

    current = await get_current_assignment(user.id)
    submitted_count = await get_submitted_count(user.id)

    logger.debug(
        f"TASK_VIEW | {user_ctx(user)} "
        f"has_current={bool(current)} submitted={submitted_count}"
    )

    sections = []
    assignment_id = None

    if current:
        assignment_id = current.id
        task = current.task

        if current:
            assignment_id = current.id
            task = current.task

            persona_map = {
                "M": "👨 Мужское",
                "F": "👩 Женское",
                None: "🧑 Не важно",
            }

            persona_label = persona_map.get(task.required_gender, "Не указано")

            example_block = (
                f"\n\n✍️ <b>Пример отзыва:</b>\n{task.example_text}"
                if task.example_text
                else ""
            )

            sections.append(
                "🟢 <b>Текущее задание</b>\n"
                f"📝 {task.text}"
                f"{example_block}\n\n"
                f"👤 <b>От какого лица:</b> {persona_label}\n"
                f"🔗 <a href='{task.link}'>Перейти</a>"
            )

    if submitted_count:
        sections.append(
            f"⏳ <b>Ожидают проверки</b>: "
            f"{submitted_count}/{settings.max_active_assignments}"
        )

    if not sections:
        sections.append("У вас нет активных заданий.")

    return {
        "state": "assigned" if current else "empty",
        "title": "📦 Задания",
        "text": "\n\n".join(sections),
        "assignment_id": assignment_id,
        "has_submitted": submitted_count > 0,
    }


# report flow
async def start_report(
    callback: CallbackQuery, button: Button, dialog_manager: DialogManager
):
    user = await load_user(dialog_manager)
    data = await tasks_getter(dialog_manager)

    assignment_id = data.get("assignment_id")

    if not assignment_id:
        await callback.answer("Нет активного задания.", show_alert=True)
        return

    logger.info(f"REPORT_START | {user_ctx(user)} assignment_id={assignment_id}")

    dialog_manager.dialog_data["assignment_id"] = assignment_id
    await dialog_manager.switch_to(TasksSG.report_account)


async def save_account(
    message: Message, widget: TextInput, dialog_manager: DialogManager, value: str
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


async def save_photo(
    message: Message, widget: MessageInput, dialog_manager: DialogManager
):
    user = await load_user(dialog_manager)

    assignment_id = dialog_manager.dialog_data["assignment_id"]

    logger.info(f"REPORT_SUBMIT | {user_ctx(user)} assignment_id={assignment_id}")

    payload = await submit_report(
        assignment_id=assignment_id,
        account_name=dialog_manager.dialog_data["account_name"],
        photo_file_id=message.photo[-1].file_id,
    )

    await notify_admins_about_report(message.bot, payload)

    logger.info(f"REPORT_NOTIFY_ADMINS | assignment_id={assignment_id}")

    await dialog_manager.start(TasksSG.empty, mode=StartMode.RESET_STACK)

    dialog_msg = dialog_manager.middleware_data.get("message")
    if dialog_msg:
        await save_assignment_report_message_id(
            assignment_id=payload["assignment"]["id"],
            message_id=dialog_msg.message_id,
        )


async def invalid_photo(
    message: Message, widget: MessageInput, dialog_manager: DialogManager
):
    await message.answer(
        "❗ Пожалуйста, отправьте <b>фото</b>.",
        parse_mode=ParseMode.HTML,
    )


async def back_to_menu(
    callback: CallbackQuery, button: Button, dialog_manager: DialogManager
):
    await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


tasks_dialog = Dialog(
    Window(
        Format("<b>{title}</b>\n\n{text}"),
        CustomEmojiButton(
            Const("📦 Получить задание"),
            id="get",
            on_click=get_task,
            style="primary",
            when=lambda d, *_: d["state"] == "empty",
        ),
        CustomEmojiButton(
            Const("📤 Отправить отчёт"),
            id="report",
            on_click=start_report,
            style="success",
            when=lambda d, *_: d["state"] == "assigned",
        ),
        CustomEmojiButton(
            Const("⏳ Задания в обработке"),
            id="review",
            on_click=lambda c, b, d: d.switch_to(TasksSG.review_list),
            when=lambda d, *_: d.get("has_submitted"),
        ),
        Button(Const("⬅️ В меню"), id="menu", on_click=back_to_menu),
        getter=tasks_getter,
        state=TasksSG.empty,
        disable_web_page_preview=True,
    ),
    Window(
        Const("📦 <b>Откуда хотите взять задание?</b>"),
        *[
            CustomEmojiButton(
                Const(title),
                id=key,
                on_click=choose_source,
                icon_custom_emoji_id=emoji_id,
            )
            for key, (title, _, emoji_id) in SOURCE_MAP.items()
        ],
        Button(Const("⬅️ В меню"), id="menu", on_click=back_to_menu),
        state=TasksSG.choose_source,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    ),
    Window(
        Const("✍️ <b>От какого лица хотите написать отзыв?</b>"),
        Button(Const("👨 Мужского"), id="male", on_click=choose_gender),
        Button(Const("👩 Женского"), id="female", on_click=choose_gender),
        Button(Const("🧑 Не важно"), id="any", on_click=choose_gender),
        Button(
            Const("⬅️ Назад"),
            id="back",
            on_click=lambda c, b, d: d.switch_to(TasksSG.choose_source),
        ),
        state=TasksSG.choose_gender,
        disable_web_page_preview=True,
    ),
    Window(
        Const("✍️ Укажите имя аккаунта:"),
        TextInput(id="account", on_success=save_account),
        state=TasksSG.report_account,
        disable_web_page_preview=True,
    ),
    Window(
        Const("📸 Отправьте фото-подтверждение:"),
        MessageInput(func=save_photo, filter=F.photo),
        MessageInput(func=invalid_photo),
        state=TasksSG.report_photo,
        disable_web_page_preview=True,
    ),
    Window(
        Format("<b>⏳ Задания в обработке</b>\n\n{text}"),
        Button(
            Const("⬅️ Назад"),
            id="back",
            on_click=lambda c, b, d: d.switch_to(TasksSG.empty),
        ),
        state=TasksSG.review_list,
        getter=review_list_getter,  # 👈 ВАЖНО
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    ),
)
