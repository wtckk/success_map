from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def user_approval_keyboard(user_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Принять",
                    callback_data=f"user_approve:{user_id}",
                    style="success",
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=f"user_reject:{user_id}",
                    style="danger",
                ),
            ]
        ]
    )


def go_main_menu_kb() -> InlineKeyboardMarkup:
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
