from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.bot.keyboards.user_approval import user_approval_keyboard, go_main_menu_kb
from app.models.user import User

import logging

from aiogram import Bot

from app.bot.keyboards.admin_review import admin_review_keyboard

from app.core.settings import settings
from app.repository.task_admin_message import save_admin_message
from app.repository.user import save_approval_admin_message

logger = logging.getLogger(__name__)


async def notify_admins_user_registered(
    bot: Bot,
    user: User,
) -> None:
    """
    Уведомляет администраторов о завершённой регистрации пользователя.

    Args:
        bot (Bot): Экземпляр бота.
        user (User): Зарегистрированный пользователь.
    """
    referrer_text = "—"

    if user.tg_id in settings.admin_id_list:
        logger.info(
            "Администратор %s зарегистрирован — approval не требуется",
            user.tg_id,
        )
        return
    if user.referrer:
        referrer_text = (
            f"{user.referrer.full_name or 'Без имени'} "
            f"(@{user.referrer.username or user.referrer.tg_id})"
        )

    text = (
        "🕓 <b>Пользователь ожидает проверки</b>\n\n"
        f"👤 ФИО: {user.full_name}\n"
        f"📞 Телефон: {user.phone}\n"
        f"🏙 Город: {user.city.name if user.city else '—'}\n"
        f"⚧ Пол: {'Мужской' if user.gender == 'M' else 'Женский'}\n"
        f"🆔 Telegram ID: <code>{user.tg_id}</code>\n"
        f"🔗 Пригласил: {referrer_text}\n\n"
        "Статус: ⏳ <b>Ожидает решения администратора</b>"
    )

    for admin_id in settings.admin_id_list:
        try:
            msg = await bot.send_message(
                chat_id=admin_id,
                text=text,
                reply_markup=user_approval_keyboard(str(user.id)),
                parse_mode=ParseMode.HTML,
            )

            await save_approval_admin_message(
                user_id=user.id,
                admin_tg_id=admin_id,
                message_id=msg.message_id,
            )

        except Exception:
            logger.exception(
                "Не удалось отправить уведомление админу %s",
                admin_id,
            )


async def notify_admins_about_report(bot: Bot, payload: dict) -> None:
    username = payload["user"]["username"]
    username_str = f"@{username}" if username else "без username"

    city_name = payload["city"]["name"] if payload.get("city") else "—"
    persona_map = {
        "M": "👨 Мужского",
        "F": "👩 Женского",
        None: "🧑 Не важно",
    }

    persona_text = persona_map.get(payload["task"].get("required_gender"), "🧑 Не указано")
    text = (
        "📤 <b>Новый отчёт</b>\n\n"
        f"👤 Пользователь: {payload['user']['full_name'] or '—'} ({username_str})\n"
        f"🆔 Telegram ID: <code>{payload['user']['tg_id']}</code>\n\n"
        f"📦 <b>ТЗ задания</b>:\n"
        f"{payload['task']['text']}\n\n"
        + (
            f"✍️ <b>Текст задания:</b>\n{payload['task']['example_text']}\n\n"
            if payload["task"]["example_text"]
            else ""
        )
        + f"🗣 <b>От какого лица нужно было оставить отзыв:</b> {persona_text}\n\n"
        + f"🔗 <b>Ссылка:</b> {payload['task']['link']}\n"
        f"👤 Аккаунт: <code>{payload['report']['account_name']}</code>\n"
        f"🏙 Город: {city_name}"
    )

    for admin_id in settings.admin_id_list:
        try:
            msg = await bot.send_photo(
                chat_id=admin_id,
                photo=payload["report"]["photo_file_id"],
                caption=text,
                reply_markup=admin_review_keyboard(
                    assignment_id=str(payload["assignment"]["id"])
                ),
                parse_mode=ParseMode.HTML,
            )

            await save_admin_message(
                assignment_id=payload["assignment"]["id"],
                admin_tg_id=admin_id,
                message_id=msg.message_id,
            )
        except Exception:
            logger.exception(
                "Не удалось отправить отчёт админу admin_id=%s",
                admin_id,
            )


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ В меню",
                    callback_data="go_main_menu",
                )
            ]
        ]
    )


async def notify_user_about_review(
    bot: Bot,
    *,
    tg_id: int,
    approved: bool,
    task_text: str,
):
    if approved:
        text = (
            "✅ <b>Отчёт принят</b>\n\n"
            f"📦 Задание: <b>{task_text}</b>\n\n"
            "Спасибо за выполнение задания!\n"
            "Вы можете взять новое задание в разделе «Задания»."
        )
    else:
        text = (
            "❌ <b>Отчёт отклонён</b>\n\n"
            f"📦 Задание: <b>{task_text}</b>\n\n"
            "К сожалению, отчёт не прошёл проверку.\n"
        )

    try:
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_menu_kb(),
        )
    except Exception:
        logger.exception(
            "Не удалось отправить уведомление пользователю tg_id=%s",
            tg_id,
        )


async def notify_user_about_approval(
    bot: Bot,
    *,
    tg_id: int,
    approved: bool,
    comment: str | None = None,
):
    if tg_id in settings.admin_id_list:
        return
    if approved:
        text = "✅ <b>Регистрация одобрена</b>\n\nДобро пожаловать!"
        reply_markup_menu = go_main_menu_kb()
    else:
        text = (
            "❌ <b>Регистрация отклонена</b>\n\n"
            "К сожалению, администратор отклонил вашу заявку."
        )

        if comment:
            text += f"\n\n💬 <b>Комментарий:</b>\n{comment}"

        text += "\n\nЕсли вы считаете, что это ошибка — обратитесь к администратору."

    try:
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup_menu,
        )
    except Exception:
        logger.exception(
            "Не удалось отправить approval-уведомление пользователю tg_id=%s",
            tg_id,
        )
