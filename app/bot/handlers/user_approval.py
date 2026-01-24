import logging
import uuid

from aiogram import Router, Bot
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from datetime import datetime

from app.bot.utils.tg import notify_user_about_approval
from app.repository.user import (
    approve_user,
    reject_user,
    get_approval_messages_by_user,
    get_user_tg_id,
    get_user_by_id,
)

from app.repository.admin import EKB_TZ

logger = logging.getLogger(__name__)
router = Router()


async def update_user_approval_messages(
    bot: Bot,
    *,
    user_id,
    approved: bool,
    admin_tg_id: int,
):
    messages = await get_approval_messages_by_user(user_id=user_id)
    user = await get_user_by_id(user_id=user_id)

    status = (
        "✅ <b>Пользователь одобрен</b>"
        if approved
        else "❌ <b>Пользователь отклонён</b>"
    )
    time_str = datetime.now(EKB_TZ).strftime("%Y-%m-%d %H:%M")

    referrer_text = "—"
    if user.referrer:
        referrer_text = (
            f"{user.referrer.full_name or 'Без имени'} "
            f"(@{user.referrer.username or user.referrer.tg_id})"
        )

    text = (
        f"{status}\n\n"
        f"👤 ФИО: {user.full_name}\n"
        f"📞 Телефон: {user.phone}\n"
        f"🏙 Город: {user.city.name if user.city else '—'}\n"
        f"⚧ Пол: {'Мужской' if user.gender == 'M' else 'Женский'}\n"
        f"🆔 Telegram ID: <code>{user.tg_id}</code>\n"
        f"🔗 Пригласил: {referrer_text}\n\n"
        f"👮 Администратор: <code>{admin_tg_id}</code>\n"
        f"🕒 Время: {time_str}"
    )

    for msg in messages:
        try:
            await bot.edit_message_text(
                chat_id=msg.admin_tg_id,
                message_id=msg.message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=None,
            )
        except Exception:
            pass


@router.callback_query(lambda c: c.data.startswith("user_approve:"))
async def approve_user_cb(c: CallbackQuery, bot: Bot):
    user_id = uuid.UUID(c.data.split(":", 1)[1])
    tg_id = await get_user_tg_id(user_id=user_id)
    if not tg_id:
        await c.answer("⚠️ Пользователь не найден", show_alert=True)
        return
    admin_id = c.from_user.id

    ok = await approve_user(
        tg_id=tg_id,
        admin_tg_id=admin_id,
    )

    if not ok:
        await c.answer("⚠️ Уже обработано", show_alert=True)
        return

    await update_user_approval_messages(
        bot,
        user_id=user_id,
        approved=True,
        admin_tg_id=admin_id,
    )
    tg_id = await get_user_tg_id(user_id=user_id)
    if tg_id:
        await notify_user_about_approval(
            bot,
            tg_id=tg_id,
            approved=True,
        )

    await c.answer("✅ Пользователь одобрен")


@router.callback_query(lambda c: c.data.startswith("user_reject:"))
async def reject_user_cb(c: CallbackQuery, bot: Bot):
    user_id = uuid.UUID(c.data.split(":", 1)[1])
    tg_id = await get_user_tg_id(user_id=user_id)
    if not tg_id:
        await c.answer("⚠️ Пользователь не найден", show_alert=True)
        return
    admin_id = c.from_user.id

    ok = await reject_user(
        tg_id=tg_id,
        admin_tg_id=admin_id,
    )

    if not ok:
        await c.answer("⚠️ Пользователь уже обработан", show_alert=True)
        return

    await update_user_approval_messages(
        bot,
        user_id=user_id,
        approved=False,
        admin_tg_id=admin_id,
    )

    tg_id = await get_user_tg_id(user_id=user_id)
    if tg_id:
        await notify_user_about_approval(
            bot,
            tg_id=tg_id,
            approved=False,
        )

    await c.answer("❌ Пользователь отклонён")
