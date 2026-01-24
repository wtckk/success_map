from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks.admin import AdminReviewCB


def admin_review_keyboard(assignment_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    kb.button(
        text="✅ Одобрить",
        callback_data=AdminReviewCB(
            action="approve",
            assignment_id=assignment_id,
        ),
    )
    kb.button(
        text="❌ Отклонить",
        callback_data=AdminReviewCB(
            action="reject",
            assignment_id=assignment_id,
        ),
    )

    kb.adjust(2)
    return kb.as_markup()
