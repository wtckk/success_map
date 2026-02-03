from __future__ import annotations

import logging
import uuid

from aiogram import F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from aiogram_dialog import (
    Dialog,
    Window,
    DialogManager,
    StartMode,
)
from aiogram_dialog.widgets.input import TextInput, MessageInput
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import (
    Select,
    Row,
    Button,
    ScrollingGroup,
)

from app.bot.dialogs.states import RegistrationSG, MainMenuSG
from app.bot.utils.tg import notify_admins_user_registered
from app.core.settings import settings
from app.repository.city import get_all_cities
from app.repository.user import (
    get_user_by_tg_id,
    update_user_profile,
)

logger = logging.getLogger(__name__)


def phone_keyboard() -> ReplyKeyboardMarkup:
    """
    Создаёт клавиатуру для отправки номера телефона через Telegram.

    Returns:
        ReplyKeyboardMarkup: Клавиатура с кнопкой отправки контакта.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="📞 Отправить номер телефона",
                    request_contact=True,
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def on_full_name(
    message: Message,
    widget: TextInput,
    dialog_manager: DialogManager,
    value: str,
) -> None:
    """
    Обрабатывает ввод ФИО пользователя.
    """
    full_name = value.strip()

    if len(full_name) < 5:
        await message.answer(
            "❗ Похоже, имя слишком короткое.\n"
            "Пожалуйста, укажите фамилию, имя и отчество."
        )
        return

    dialog_manager.dialog_data["full_name"] = full_name
    logger.info("Регистрация: ФИО получено")

    await message.answer(
        "📞 Нажмите кнопку ниже, чтобы отправить номер телефона:",
        reply_markup=phone_keyboard(),
    )

    await dialog_manager.switch_to(RegistrationSG.phone)


async def on_phone_contact(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """
    Обрабатывает получение номера телефона через Telegram contact.
    """
    if not message.contact or not message.contact.phone_number:
        await message.answer("❗ Не удалось получить номер телефона.")
        return

    dialog_manager.dialog_data["phone"] = message.contact.phone_number
    logger.info("Регистрация: телефон получен через Telegram")

    await message.answer(
        "✅ Отлично, номер получен.",
        reply_markup=ReplyKeyboardRemove(),
    )

    await dialog_manager.switch_to(RegistrationSG.city)


async def cities_getter(
    dialog_manager: DialogManager,
    **kwargs,
) -> dict:
    """
    Возвращает список городов для выбора.
    """
    cities = await get_all_cities()
    return {"cities": cities}


async def on_city_selected(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    city_id: uuid.UUID,
) -> None:
    """
    Обрабатывает выбор города.
    """
    dialog_manager.dialog_data["city_id"] = city_id
    logger.info("Регистрация: город выбран %s", city_id)

    await dialog_manager.switch_to(RegistrationSG.gender)


async def on_gender_selected(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    gender: str,
) -> None:
    """
    Завершает регистрацию пользователя и отправляет его в главное меню.
    """
    tg_id = callback.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        logger.error(
            "Регистрация: пользователь не найден tg_id=%s",
            tg_id,
        )
        await callback.message.answer("❗ Ошибка регистрации. Попробуйте снова: /start")
        await dialog_manager.done()
        return

    await update_user_profile(
        user_id=user.id,
        full_name=dialog_manager.dialog_data["full_name"],
        phone=dialog_manager.dialog_data["phone"],
        city_id=dialog_manager.dialog_data["city_id"],
        gender=gender,
    )

    bot: Bot = dialog_manager.middleware_data["bot"]
    user = await get_user_by_tg_id(tg_id)
    await notify_admins_user_registered(bot, user)

    logger.info("Регистрация завершена для tg_id=%s", tg_id)

    if user.tg_id in settings.admin_id_list:
        await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)
    else:
        await dialog_manager.start(
            RegistrationSG.waiting,
            mode=StartMode.RESET_STACK,
        )


registration_dialog = Dialog(
    Window(
        Const(
            "👤 <b>Регистрация</b>\n\n"
            "Как вас зовут?\n\n"
            "Укажите фамилию, имя и отчество."
        ),
        TextInput(
            id="full_name",
            on_success=on_full_name,
        ),
        state=RegistrationSG.full_name,
    ),
    Window(
        Const(
            "📞 <b>Контактный номер</b>\n\n"
            "Номер телефона нужен для подтверждения выполненных заданий."
        ),
        MessageInput(
            func=on_phone_contact,
            filter=F.contact,
        ),
        state=RegistrationSG.phone,
    ),
    Window(
        Const(
            "🏙 <b>Город выполнения заданий</b>\n\n"
            "Выберите город, в котором вы планируете выполнять задания."
        ),
        ScrollingGroup(
            Select(
                text=Format("{item.name}"),
                items="cities",
                item_id_getter=lambda city: city.id,
                id="city",
                on_click=on_city_selected,
            ),
            id="cities_scroll",
            width=1,
            height=6,
        ),
        getter=cities_getter,
        state=RegistrationSG.city,
    ),
    Window(
        Const("⚧ <b>Уточним ещё один момент</b>\n\nВыберите ваш пол:"),
        Row(
            Button(
                Const("Мужской"),
                id="male",
                on_click=lambda c, w, m: on_gender_selected(c, w, m, "M"),
            ),
            Button(
                Const("Женский"),
                id="female",
                on_click=lambda c, w, m: on_gender_selected(c, w, m, "F"),
            ),
        ),
        state=RegistrationSG.gender,
    ),
    Window(
        Const(
            "⏳ <b>Заявка на регистрацию отправлена</b>\n\n"
            "Ваши данные проверяются администратором.\n\n"
            "Как только доступ будет открыт — "
            "мы сразу вас уведомим."
        ),
        state=RegistrationSG.waiting,
    ),
)
