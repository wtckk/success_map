import asyncio
import logging
import uuid
from typing import Any

from aiogram import F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.input import TextInput, MessageInput
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import (
    Select,
    Row,
    Button,
    ScrollingGroup,
    Back,
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


# helpers

def progress_header(step: int, total: int = 4) -> str:
    return f"👤 <b>Создание профиля</b>\n\nШаг {step} из {total}\n\n"


def phone_keyboard() -> ReplyKeyboardMarkup:
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


# handlers

async def on_full_name(
    message: Message,
    widget: TextInput,
    dialog_manager: DialogManager,
    value: str,
) -> None:
    full_name = value.strip()

    if len(full_name) < 5 or len(full_name.split()) < 2:
        await message.answer(
            "❗ Пожалуйста, укажите минимум <b>фамилию</b> и <b>имя</b>.\n"
            "Например: <i>Иванов Иван</i>",
        )
        return

    dialog_manager.dialog_data["full_name"] = full_name
    logger.info("Регистрация: ФИО получено")

    await message.answer(
        "✅ Отлично!\n\nТеперь укажем способ связи 👇",
        reply_markup=phone_keyboard(),
    )
    await dialog_manager.switch_to(RegistrationSG.phone)


async def on_phone_contact(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    if not message.contact or not message.contact.phone_number:
        await message.answer(
            "❗ Используйте кнопку «📞 Отправить номер телефона» ниже."
        )
        return

    dialog_manager.dialog_data["phone"] = message.contact.phone_number
    logger.info("Регистрация: телефон получен через Telegram")

    await message.answer(
        "🔒 Номер сохранён.\n\nПродолжаем регистрацию 👇",
        reply_markup=ReplyKeyboardRemove(),
    )
    await dialog_manager.switch_to(RegistrationSG.city)


async def cities_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict:
    cities = await get_all_cities()
    logger.info("Cities loaded: %s", len(cities))
    return {"cities": cities}


async def on_city_selected(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    city_id: str,  # ВСЕГДА строка из callback
) -> None:
    dialog_manager.dialog_data["city_id"] = city_id  # сохраняем как str
    logger.info("Регистрация: город выбран %s", city_id)

    await callback.answer("✔ Город выбран")
    await dialog_manager.switch_to(RegistrationSG.gender)


async def on_gender_selected(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    gender: str,
) -> None:
    dialog_manager.dialog_data["gender"] = gender
    logger.info("Регистрация: пол выбран %s", gender)

    await callback.answer("✔ Принято")
    await dialog_manager.switch_to(RegistrationSG.confirm)


async def confirm_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict:
    cities = await get_all_cities()

    city_id_str = dialog_manager.dialog_data.get("city_id")
    city_name = "Не выбран"

    if city_id_str:
        try:
            city_uuid = uuid.UUID(city_id_str)
            city_name = next(
                (c.name for c in cities if c.id == city_uuid),
                "Не выбран",
            )
        except Exception:
            logger.exception("Ошибка при определении города")

    gender_map = {"M": "Мужской", "F": "Женский"}
    gender_ui = gender_map.get(
        dialog_manager.dialog_data.get("gender"),
        "Не указан",
    )

    return {
        "full_name": dialog_manager.dialog_data.get("full_name", "—"),
        "phone": dialog_manager.dialog_data.get("phone", "—"),
        "city_name": city_name,
        "gender": gender_ui,
    }


async def finalize_registration(
    callback: CallbackQuery,
    button: Button,
    dialog_manager: DialogManager,
) -> None:
    await callback.message.edit_text("⏳ Сохраняем профиль...")
    await asyncio.sleep(0.4)
    await callback.message.edit_text("🔍 Проверяем данные...")
    await asyncio.sleep(0.4)
    await callback.message.edit_text("🚀 Почти готово...")
    await asyncio.sleep(0.4)

    tg_id = callback.from_user.id
    user = await get_user_by_tg_id(tg_id)

    if not user:
        logger.error("Пользователь не найден tg_id=%s", tg_id)
        await callback.message.answer(
            "❗ Ошибка регистрации. Попробуйте снова: /start"
        )
        await dialog_manager.done()
        return

    try:
        city_id = uuid.UUID(dialog_manager.dialog_data["city_id"])

        await update_user_profile(
            user_id=user.id,
            full_name=dialog_manager.dialog_data["full_name"],
            phone=dialog_manager.dialog_data["phone"],
            city_id=city_id,
            gender=dialog_manager.dialog_data["gender"],
        )

    except Exception:
        logger.exception("Ошибка сохранения профиля tg_id=%s", tg_id)
        await callback.message.answer(
            "❗ Не удалось сохранить профиль. Попробуйте: /start"
        )
        await dialog_manager.done()
        return

    bot: Bot = dialog_manager.middleware_data["bot"]

    user = await get_user_by_tg_id(tg_id)
    if user:
        await notify_admins_user_registered(bot, user)

    logger.info("Регистрация завершена для tg_id=%s", tg_id)

    if tg_id in settings.admin_id_list:
        await dialog_manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)
    else:
        await dialog_manager.start(RegistrationSG.waiting, mode=StartMode.RESET_STACK)


registration_dialog = Dialog(
    Window(
        Const(
            progress_header(1)
            + "Как вас зовут?\n\n"
              "Введите <b>фамилию</b>, <b>имя</b> и (если есть) <b>отчество</b>.\n"
              "Например: <i>Иванов Иван Иванович</i>"
        ),
        TextInput(id="full_name", on_success=on_full_name),
        state=RegistrationSG.full_name,
    ),

    Window(
        Const(
            progress_header(2)
            + "📞 <b>Контактный номер</b>\n\n"
              "Номер нужен для подтверждения выполненных заданий\n"
              "и начисления выплат.\n\n"
              "Нажмите кнопку снизу, чтобы отправить номер."
        ),
        MessageInput(func=on_phone_contact, filter=F.contact),
        Back(Const("⬅ Назад")),
        state=RegistrationSG.phone,
    ),

    Window(
        Const(
            progress_header(3)
            + "🏙 <b>Город работы</b>\n\n"
              "Выберите город, в котором вы планируете выполнять задания:"
        ),
        ScrollingGroup(
            Select(
                text=Format("{item.name}"),
                items="cities",
                item_id_getter=lambda city: str(city.id),
                id="city",
                on_click=on_city_selected,
            ),
            id="cities_scroll",
            width=1,
            height=6,
        ),
        Back(Const("⬅ Назад")),
        getter=cities_getter,
        state=RegistrationSG.city,
    ),

    Window(
        Const(progress_header(4) + "⚧ <b>Последний шаг</b>\n\nВыберите ваш пол:"),
        Row(
            Button(
                Const("👨 Мужской"),
                id="male",
                on_click=lambda c, w, m: on_gender_selected(c, w, m, "M"),
            ),
            Button(
                Const("👩 Женский"),
                id="female",
                on_click=lambda c, w, m: on_gender_selected(c, w, m, "F"),
            ),
        ),
        Back(Const("⬅ Назад")),
        state=RegistrationSG.gender,
    ),

    Window(
        Format(
            "📋 <b>Проверьте данные</b>\n\n"
            "👤 <b>ФИО:</b> {full_name}\n"
            "📞 <b>Телефон:</b> {phone}\n"
            "🏙 <b>Город:</b> {city_name}\n"
            "⚧ <b>Пол:</b> {gender}\n\n"
            "Всё верно?"
        ),
        Row(
            Back(Const("✏ Изменить")),
            Button(
                Const("✅ Подтвердить"),
                id="confirm",
                on_click=finalize_registration,
            ),
        ),
        getter=confirm_getter,
        state=RegistrationSG.confirm,
    ),

    Window(
        Const(
            "🎉 <b>Профиль создан!</b>\n\n"
            "Ваша заявка отправлена администратору.\n\n"
            "⏳ Обычно проверка занимает до 30 минут.\n"
            "Мы уведомим вас сразу после одобрения."
        ),
        state=RegistrationSG.waiting,
    ),
)