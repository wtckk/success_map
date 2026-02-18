import logging

from aiogram import Router, F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

from aiogram_dialog import DialogManager, StartMode

from app.models.user import UserApprovalStatus
from app.repository.user import get_user_by_tg_id, create_user
from app.bot.dialogs.states import RegistrationSG, MainMenuSG

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart())
async def start_handler(
    message: Message,
    dialog_manager: DialogManager,
) -> None:
    tg_id = message.from_user.id
    username = message.from_user.username
    start_arg = message.text.split(maxsplit=1)

    user = await get_user_by_tg_id(tg_id=tg_id)

    referrer = None
    if len(start_arg) > 1 and start_arg[1].startswith("ref_"):
        try:
            ref_tg_id = int(start_arg[1].replace("ref_", ""))
            if ref_tg_id != tg_id:
                referrer = await get_user_by_tg_id(ref_tg_id)
        except ValueError:
            pass

    if not user:
        user = await create_user(
            tg_id=tg_id,
            username=username,
            referrer_id=referrer.id if referrer else None,
        )

        if referrer:
            await message.answer(
                "🎁 <b>Вы пришли по приглашению!</b>\n\n",
                parse_mode=ParseMode.HTML,
            )

    if user.full_name:
        if user.approval_status == UserApprovalStatus.APPROVED:
            await message.answer(
                "👋 <b>С возвращением!</b>\n\nРады видеть вас снова 🚀",
                parse_mode=ParseMode.HTML,
            )
            await dialog_manager.start(
                MainMenuSG.main,
                mode=StartMode.RESET_STACK,
            )
        else:
            await message.answer(
                "⏳ <b>Заявка на проверке</b>\n\n"
                "Администратор ещё рассматривает вашу регистрацию.\n\n"
                "Мы уведомим вас после одобрения.",
                parse_mode=ParseMode.HTML,
            )
            await dialog_manager.start(
                RegistrationSG.waiting,
                mode=StartMode.RESET_STACK,
            )
        return

    await message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Этот бот помогает выполнять задания и получать выплаты 💰\n\n"
        "Регистрация займёт меньше 1 минуты.",
        parse_mode=ParseMode.HTML,
    )

    await message.answer(
        "🚀 <b>Начнём создание профиля?</b>",
        parse_mode=ParseMode.HTML,
    )

    await dialog_manager.start(
        RegistrationSG.full_name,
        mode=StartMode.RESET_STACK,
    )


@router.callback_query(F.data == "go_main_menu")
async def go_main_menu_handler(
    callback: CallbackQuery,
    dialog_manager: DialogManager,
):
    await callback.answer()

    await dialog_manager.start(
        MainMenuSG.main,
        mode=StartMode.RESET_STACK,
    )
