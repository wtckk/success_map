import asyncio
from html import escape

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.bot.keyboards.user_approval import user_approval_keyboard, go_main_menu_kb
from app.models.user import User

import logging

from aiogram import Bot, Dispatcher

from app.bot.keyboards.admin_review import admin_review_keyboard

from app.core.settings import settings
from app.repository.task_admin_message import save_admin_message
from app.repository.user import save_approval_admin_message

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


def get_source_emoji_html(source: str) -> str:
    for _, (title, _, emoji_id) in SOURCE_MAP.items():
        if title == source:
            return f'<tg-emoji emoji-id="{emoji_id}">🗺</tg-emoji>'
    return "🗺"


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
    username = f"@{user.username or user.tg_id}"
    text = (
        "🕓 <b>Пользователь ожидает проверки</b>\n\n"
        f"👤 ФИО: {user.full_name} ({username})\n"
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
    username = payload["user"].get("username")
    username_str = f"@{username}" if username else "—"
    assignment_id = str(payload["assignment"]["id"])

    city_name = payload["city"]["name"] if payload.get("city") else "—"

    persona_map = {
        "M": "👨 Мужского",
        "F": "👩 Женского",
        None: "🧑 Не важно",
    }

    persona_text = persona_map.get(
        payload["task"].get("required_gender"), "🧑 Не указано"
    )

    source = payload["task"].get("source")
    source_emoji = get_source_emoji_html(source)

    link = escape(payload["task"]["link"])

    text = (
        "📤 <b>Новый отчёт</b>\n\n"
        f"{source_emoji} <code>{payload['task']['human_code']}</code>\n\n"
        f"✍️ <b>Текст отзыва:</b>\n"
        f"<pre>{escape(payload['task']['example_text'])}</pre>\n\n"
        f"👤 <b>Аккаунт в отзыве:</b> "
        f"<code>{escape(payload['report']['account_name'])}</code>\n"
        f'🔗 <a href="{link}">Перейти</a>\n'
        f"🗣 <b>От какого лица:</b> {persona_text}\n\n"
        f"👤 <b>Исполнитель:</b> "
        f"{escape(payload['user']['full_name'] or '—')} ({username_str})\n"
        f"📱 TG ID: <code>{payload['user']['tg_id']}</code>\n"
        f"📌 Assignment: <code>{payload['assignment']['id']}</code>\n"
        f"📅 Отправлено: "
        f"{payload['assignment']['submitted_at'].strftime('%d.%m.%Y %H:%M')}\n"
        f"🏙 Город: {escape(city_name)}"
    )

    for admin_id in settings.admin_id_list:
        try:
            msg = await bot.send_photo(
                chat_id=admin_id,
                photo=payload["report"]["photo_file_id"],
                caption=text,
                reply_markup=admin_review_keyboard(assignment_id=assignment_id),
                parse_mode=ParseMode.HTML,
            )

            await save_admin_message(
                assignment_id=assignment_id,
                admin_tg_id=admin_id,
                message_id=msg.message_id,
            )

        except Exception:
            logger.exception(
                "REPORT_NOTIFY_ERROR | admin_id=%s assignment_id=%s",
                admin_id,
                assignment_id,
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
    dispatcher: Dispatcher,
    *,
    tg_id: int,
    approved: bool,
    human_code: str,
    source: str,
    reason: str | None = None,
):
    source_emoji = get_source_emoji_html(source)

    if approved:
        text = (
            "✅ <b>Отчёт принят</b>\n\n"
            f"{source_emoji} <code>{human_code}</code>\n\n"
            "Ваш отчёт успешно прошёл проверку.\n"
            "Вы можете взять новое задание в разделе <b>«Задания»</b>."
        )
    else:
        reason_block = f"\n\n💬 <b>Причина:</b>\n{escape(reason)}" if reason else ""

        text = (
            "❌ <b>Отчёт отклонён</b>\n\n"
            f"{source_emoji} <code>{human_code}</code>\n"
            f"{reason_block}\n\n"
            "Вы можете взять новое задание в разделе <b>«Задания»</b>."
        )

    try:
        await bot.send_message(
            chat_id=tg_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )

        await asyncio.sleep(0.8)

        await bot.send_message(
            chat_id=tg_id,
            text="Вы можете продолжить работу:",
            reply_markup=back_to_menu_kb(),
        )

        logger.info(f"REVIEW_NOTIFY_USER | tg_id={tg_id} approved={approved}")

        logger.info(f"REVIEW_NOTIFY_USER | tg_id={tg_id} approved={approved}")

    except Exception:
        logger.exception(f"REVIEW_NOTIFY_ERROR | tg_id={tg_id}")


async def notify_user_about_approval(
    bot: Bot,
    *,
    tg_id: int,
    approved: bool,
    comment: str | None = None,
):
    if tg_id in settings.admin_id_list:
        return

    reply_markup_menu = None

    if approved:
        text = (
            "🎉 <b>Регистрация одобрена!</b>\n\n"
            "Добро пожаловать в систему 👋\n\n"
            "Теперь вам доступны задания.\n\n"
            "💰 Начните выполнять и зарабатывать уже сейчас."
        )

        reply_markup_menu = go_main_menu_kb()

    else:
        text = (
            "❌ <b>Регистрация не одобрена</b>\n\n"
            "К сожалению, администратор отклонил вашу заявку."
        )

        if comment:
            text += f"\n\n💬 <b>Комментарий администратора:</b>\n{comment}"

        text += (
            "\n\nЕсли вы считаете, что произошла ошибка, свяжитесь с администратором."
        )

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
