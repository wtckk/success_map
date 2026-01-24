from aiogram.filters.callback_data import CallbackData


class AdminReviewCB(CallbackData, prefix="review"):
    action: str  # approve | reject
    assignment_id: str
