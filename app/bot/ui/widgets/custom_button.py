from typing import Optional

from aiogram.types import InlineKeyboardButton
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.api.protocols import DialogManager


class CustomEmojiButton(Button):
    def __init__(
        self,
        text,
        id: str,
        on_click=None,
        icon_custom_emoji_id: Optional[str] = None,
        when=None,
    ):
        super().__init__(text=text, id=id, on_click=on_click, when=when)
        self.icon_custom_emoji_id = icon_custom_emoji_id

    async def _render_keyboard(
        self,
        data: dict,
        manager: DialogManager,
    ):
        return [
            [
                InlineKeyboardButton(
                    text=await self.text.render_text(data, manager),
                    callback_data=self._own_callback_data(),  # ← ВАЖНО
                    icon_custom_emoji_id=self.icon_custom_emoji_id,
                ),
            ],
        ]
