from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Row, Url
from aiogram_dialog.widgets.text import Format, Const
import asyncio

from app.bot.dialogs.states import SubscriptionSG, MainMenuSG
from app.repository.user import mark_user_channel_verified
from app.core.settings import settings


async def subscription_getter(dialog_manager: DialogManager, **kwargs):
    status = dialog_manager.dialog_data.get("status", "idle")

    if status == "checking":
        text = "⏳ <b>Проверяю подписку...</b>\n\nПожалуйста, подождите..."

    elif status == "almost":
        text = "🔄 <b>Почти готово...</b>\n\nСекунду..."

    elif status == "success":
        text = (
            "✅ <b>Подписка подтверждена!</b>\n\n"
            "Доступ к боту открыт.\n"
            "Перенаправляю в главное меню..."
        )

    elif status == "error":
        text = (
            "❌ <b>Подписка не обнаружена</b>\n\n"
            "Убедитесь, что вы подписались на канал\n"
            "и попробуйте снова."
        )

    else:
        text = (
            "🔐 <b>Доступ к боту открыт для подписчиков</b>\n\n"
            "1️⃣ Подпишитесь на наш канал\n"
            "2️⃣ Вернитесь и нажмите кнопку ниже"
        )

    return {"subscription_text": text}


async def check_subscription(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
):
    bot = dialog_manager.middleware_data["bot"]
    tg_id = callback.from_user.id

    dialog_manager.dialog_data["status"] = "checking"
    await dialog_manager.update({})

    await asyncio.sleep(0.6)

    dialog_manager.dialog_data["status"] = "almost"
    await dialog_manager.update({})

    await asyncio.sleep(0.6)

    try:
        member = await bot.get_chat_member(
            settings.required_channel_id,
            tg_id,
        )

        if member.status in ("member", "administrator", "creator"):
            await mark_user_channel_verified(tg_id)

            dialog_manager.dialog_data["status"] = "success"
            await dialog_manager.update({})

            await asyncio.sleep(1.0)

            await dialog_manager.start(
                MainMenuSG.main,
                mode=StartMode.RESET_STACK,
            )
            return

    except Exception:
        pass

    dialog_manager.dialog_data["status"] = "error"
    await dialog_manager.update({})


subscription_dialog = Dialog(
    Window(
        Format("{subscription_text}"),
        Row(
            Url(
                Const("📢 Открыть канал"),
                Const(settings.channel_invite_link),
            )
        ),
        Row(
            Button(
                Const("✅ Я подписался"),
                id="check",
                on_click=check_subscription,
            )
        ),
        state=SubscriptionSG.check,
        getter=subscription_getter,
    )
)
