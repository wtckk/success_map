import logging
import uuid

from aiogram import Router, Bot
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery
from datetime import datetime, timezone, timedelta


from app.bot.utils.tg import notify_user_about_approval
from app.repository.user import (
    approve_user,
    reject_user,
    get_approval_messages_by_user,
    get_user_tg_id,
    get_user_by_id,
    get_user_by_tg_id,
)

MSC_TZ = timezone(timedelta(hours=3))

logger = logging.getLogger(__name__)
router = Router()


async def update_user_approval_messages(
    bot: Bot,
    *,
    user_id,
    approved: bool,
    admin_tg_id: int,
):
    logger.info(
        "update_user_approval_messages: user_id=%s approved=%s admin_tg_id=%s",
        user_id,
        approved,
        admin_tg_id,
    )
    messages = await get_approval_messages_by_user(user_id=user_id)
    logger.info(
        "update_user_approval_messages: found %s admin-messages to edit",
        len(messages),
    )

    user = await get_user_by_id(user_id=user_id)

    if not user:
        logger.warning(
            "update_user_approval_messages: user not found user_id=%s", user_id
        )
        return

    status = (
        "✅ <b>Пользователь одобрен</b>"
        if approved
        else "❌ <b>Пользователь отклонён</b>"
    )
    time_str = datetime.now(MSC_TZ).strftime("%Y-%m-%d %H:%M")

    referrer_text = "—"
    if user.referrer:
        referrer_text = (
            f"{user.referrer.full_name or 'Без имени'} "
            f"(@{user.referrer.username or user.referrer.tg_id})"
        )
    admin = await get_user_by_tg_id(tg_id=admin_tg_id)
    text = (
        f"{status}\n\n"
        f"👤 ФИО: {user.full_name}\n"
        f"📞 Телефон: {user.phone}\n"
        f"🏙 Город: {user.city.name if user.city else '—'}\n"
        f"⚧ Пол: {'Мужской' if user.gender == 'M' else 'Женский'}\n"
        f"🆔 Telegram ID: <code>{user.tg_id}</code>\n"
        f"🔗 Пригласил: {referrer_text}\n\n"
        f"👮 Администратор: {'@' + admin.username if admin else admin_tg_id}\n"
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
            logger.info(
                "update_user_approval_messages: edited message admin_tg_id=%s message_id=%s",
                msg.admin_tg_id,
                msg.message_id,
            )
        except Exception:
            logger.exception(
                "update_user_approval_messages: failed edit admin_tg_id=%s message_id=%s",
                msg.admin_tg_id,
                msg.message_id,
            )


@router.callback_query(
    lambda c: c.data.startswith("user_approve:"), flags={"aiogram_dialog": False}
)
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
    logger.info("approve_user_cb: approve_user returned ok=%s (tg_id=%s)", ok, tg_id)

    if not ok:
        await c.answer("⚠️ Уже обработано", show_alert=True)
        return

    await update_user_approval_messages(
        bot,
        user_id=user_id,
        approved=True,
        admin_tg_id=admin_id,
    )
    await notify_user_about_approval(
        bot,
        tg_id=tg_id,
        approved=True,
    )

    await c.answer("✅ Пользователь одобрен")


@router.callback_query(
    lambda c: c.data.startswith("user_reject:"), flags={"aiogram_dialog": False}
)
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

    await notify_user_about_approval(
        bot,
        tg_id=tg_id,
        approved=False,
    )

    await c.answer("❌ Пользователь отклонён")
