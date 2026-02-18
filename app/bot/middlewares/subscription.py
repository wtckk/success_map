from aiogram import BaseMiddleware
from aiogram_dialog import DialogManager, StartMode

from app.bot.dialogs.states import SubscriptionSG
from app.core.settings import settings
from app.models.user import UserApprovalStatus
from app.repository.user import get_user_by_tg_id


from aiogram_dialog.api.exceptions import NoContextError


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        dialog_manager: DialogManager = data.get("dialog_manager")
        user_tg = getattr(event, "from_user", None)

        if not user_tg:
            return await handler(event, data)

        if user_tg.id in settings.admin_id_list:
            return await handler(event, data)

        user = await get_user_by_tg_id(user_tg.id)

        if not user or not user.full_name:
            return await handler(event, data)

        if user.approval_status != UserApprovalStatus.APPROVED:
            return await handler(event, data)

        if user.is_channel_verified:
            return await handler(event, data)

        if dialog_manager:
            try:
                context = dialog_manager.current_context()
                if context.state == SubscriptionSG.check:
                    return await handler(event, data)
            except NoContextError:
                pass

            await dialog_manager.start(
                SubscriptionSG.check,
                mode=StartMode.RESET_STACK,
            )
            return

        return await handler(event, data)
