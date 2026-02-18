import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import ExceptionTypeFilter
from aiogram_dialog import setup_dialogs, StartMode, DialogManager, ShowMode
from aiogram_dialog.api.exceptions import UnknownIntent

from app.bot.dialogs.admin import admin_dialog
from app.bot.dialogs.info_pages import (
    payments_dialog,
    rules_dialog,
    contacts_dialog,
)
from app.bot.dialogs.states import MainMenuSG
from app.bot.middlewares.approval import ApprovalMiddleware
from app.bot.middlewares.block_user import BlockUserMiddleware
from app.bot.middlewares.subscription import SubscriptionMiddleware
from app.bot.scheduler import setup_scheduler

from app.core.settings import settings


# middlewares
from app.bot.middlewares.registration import RegistrationMiddleware

# routers
from app.bot.handlers.start import router as start_router
from app.bot.handlers.admin_review import router as admin_router

# dialogs
from app.bot.dialogs.registration import registration_dialog
from app.bot.dialogs.main_menu import main_menu_dialog
from app.bot.dialogs.tasks import tasks_dialog
from app.bot.dialogs.referrals import referrals_dialog
from app.bot.dialogs.profile import profile_dialog
from app.bot.dialogs.subcription import subscription_dialog


from app.bot.handlers.user_approval import router as user_approval_router

logger = logging.getLogger(__name__)


async def on_unknown_intent(event, dialog_manager: DialogManager):
    logger.error("Restarting dialog: %s", event.exception)

    upd = event.update
    if upd and upd.callback_query:
        await upd.callback_query.answer(
            "🔄 Сессия устарела. Возвращаю в главное меню.",
            show_alert=False,
        )

    await dialog_manager.start(
        MainMenuSG.main,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.SEND,
    )


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    dp.update.middleware(RegistrationMiddleware())

    dp.message.middleware(BlockUserMiddleware())
    dp.callback_query.middleware(BlockUserMiddleware())

    dp.update.middleware(ApprovalMiddleware())

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(user_approval_router)
    dp.include_router(registration_dialog)
    dp.include_router(main_menu_dialog)
    dp.include_router(profile_dialog)
    dp.include_router(tasks_dialog)
    dp.include_router(payments_dialog)
    dp.include_router(rules_dialog)
    dp.include_router(contacts_dialog)
    dp.include_router(referrals_dialog)
    dp.include_router(admin_dialog)
    dp.include_router(subscription_dialog)
    dp.errors.register(
        on_unknown_intent,
        ExceptionTypeFilter(UnknownIntent),
    )

    scheduler = setup_scheduler(bot)
    dp.workflow_data["scheduler"] = scheduler
    setup_dialogs(dp)
    dp.message.middleware(SubscriptionMiddleware())
    dp.callback_query.middleware(SubscriptionMiddleware())

    await dp.start_polling(bot)
