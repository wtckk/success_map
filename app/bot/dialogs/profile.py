import logging
from html import escape

from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.text import Format
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.text import Const

from app.bot.dialogs.info_pages import back_to_menu
from app.bot.dialogs.states import ProfileSG, ReferralsSG
from app.bot.utils.tg import get_source_emoji_html
from app.repository.user import (
    get_profile_data,
    get_user_id_by_tg_id,
    get_approved_tasks,
)

logger = logging.getLogger(__name__)


TASKS_PER_PAGE = 5
MAX_MESSAGE_LENGTH = 3800


async def profile_getter(dialog_manager: DialogManager, **_):
    tg_id = dialog_manager.event.from_user.id
    return await get_profile_data(tg_id)


async def history_getter(dialog_manager: DialogManager, **_):
    tg_id = dialog_manager.event.from_user.id
    user_id = await get_user_id_by_tg_id(tg_id)

    all_tasks = await get_approved_tasks(user_id)

    page = dialog_manager.dialog_data.get("page", 0)
    start = page * TASKS_PER_PAGE
    end = start + TASKS_PER_PAGE

    total_pages = max((len(all_tasks) - 1) // TASKS_PER_PAGE + 1, 1)
    page_tasks = all_tasks[start:end]

    sections = []

    if not page_tasks:
        text = "📦 <b>История заданий</b>\n\nПока нет выполненных заданий."
    else:
        for task in page_tasks:
            date_str = (
                task["processed_at"].strftime("%d.%m.%Y")
                if task["processed_at"]
                else "—"
            )

            persona_map = {
                "M": "👨 Мужского",
                "F": "👩 Женского",
                None: "🧑 Не важно",
            }

            persona_label = persona_map.get(task["required_gender"], "🧑 Не указано")

            example_block = (
                f"\n\n✍️ <b>Текст отзыва:</b>\n<pre>{escape(task['example_text'])}</pre>"
                if task["example_text"]
                else ""
            )

            source_emoji = get_source_emoji_html(task["source"])

            section = (
                f"{source_emoji} <code>{task['human_code']}</code>"
                f"{example_block}\n\n"
                f"👤 <b>От какого лица:</b> {persona_label}\n"
                f"👤 <b>Аккаунт:</b> <code>{escape(task['account_name'] or '—')}</code>\n"
                f"🔗 <a href='{escape(task['link'])}'>Перейти</a>\n"
                f"📅 {date_str}"
            )

            sections.append(section)

        body = "\n\n──────────────\n\n".join(sections)

        text = (
            "📦 <b>История заданий</b>\n\n"
            + body
            + f"\n\n📄 Страница {page + 1} из {total_pages}"
        )

    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[:MAX_MESSAGE_LENGTH] + "\n\n…"

    return {
        "history_text": text,
        "has_prev": page > 0,
        "has_next": end < len(all_tasks),
    }


async def next_page(c, w, m: DialogManager):
    m.dialog_data["page"] = m.dialog_data.get("page", 0) + 1
    await m.show()


async def prev_page(c, w, m: DialogManager):
    m.dialog_data["page"] = max(m.dialog_data.get("page", 0) - 1, 0)
    await m.show()


async def go_to_history(c, w, m: DialogManager):
    m.dialog_data["page"] = 0
    await m.switch_to(ProfileSG.history)


async def back_to_profile(c, w, m: DialogManager):
    await m.switch_to(ProfileSG.main)


profile_dialog = Dialog(
    Window(
        Format(
            "<tg-emoji emoji-id='5373012449597335010'>👤</tg-emoji> "
            "<b>Профиль</b>\n\n"
            "🪪 <b>Имя:</b> {full_name}\n"
            "🏙 <b>Город:</b> {city}\n\n"
            "📊 <b>Статистика</b>\n"
            "└ 📦 Выполнено заданий: <b>{orders_count}</b>\n\n"
            "<tg-emoji emoji-id='5357122032674818130'>🤝</tg-emoji> <b>Реферальная программа</b>\n"
            "├ 👥 Приглашено: <b>{referrals_count}</b>\n"
            "└ 🔗 <b>Ваша ссылка:</b>\n"
            "<code>{referral_link}</code>"
        ),
        Row(
            Button(
                Const("📦 История заданий"),
                id="history",
                on_click=go_to_history,
            ),
            Button(
                Const("👥 Мои приглашённые"),
                id="referrals",
                on_click=lambda c, w, m: m.start(
                    ReferralsSG.main,
                    mode=StartMode.RESET_STACK,
                ),
            ),
        ),
        Button(
            Const("⬅️ В меню"),
            id="menu",
            on_click=back_to_menu,
        ),
        getter=profile_getter,
        state=ProfileSG.main,
    ),
    Window(
        Format("{history_text}"),
        Row(
            Button(
                Const("⬅️"),
                id="prev",
                when="has_prev",
                on_click=prev_page,
            ),
            Button(
                Const("➡️"),
                id="next",
                when="has_next",
                on_click=next_page,
            ),
        ),
        Button(
            Const("⬅️ В профиль"),
            id="back_profile",
            on_click=back_to_profile,
        ),
        disable_web_page_preview=True,
        getter=history_getter,
        state=ProfileSG.history,
    ),
)
