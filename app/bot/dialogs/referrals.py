from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.text import Format, Const
from aiogram_dialog.widgets.kbd import Button, Row

from app.bot.dialogs.states import ReferralsSG, ProfileSG
from app.repository.user import get_referrals_with_stats, get_user_id_by_tg_id

PAGE_SIZE = 5


async def referrals_getter(dialog_manager: DialogManager, **_):
    tg_id = dialog_manager.event.from_user.id
    user_id = await get_user_id_by_tg_id(tg_id)

    page = dialog_manager.dialog_data.get("page", 0)
    referrals = await get_referrals_with_stats(user_id)

    total = len(referrals)
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = referrals[start:end]

    if not referrals:
        return {
            "referrals_text": (
                "👥 <b>Мои приглашённые</b>\n\nУ вас пока нет приглашённых."
            ),
            "has_referrals": False,
        }

    lines = []
    for r in page_items:
        name = r["full_name"] or "—"
        username = f"@{r['username']}" if r.get("username") else "—"
        city = r["city"] or "—"

        lines.append(
            f"👤 <b>{name}</b> ({username})\n"
            f"🆔 <code>{r['tg_id']}</code>\n"
            f"🏙 Город: {city}\n"
            f"📦 Принято заданий: <b>{r['approved_tasks']}</b>"
        )

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    dialog_manager.dialog_data["page"] = page

    return {
        "referrals_text": "👥 <b>Мои приглашённые</b>\n\n" + "\n\n".join(lines),
        "page_str": f"{page + 1}/{total_pages}",
        "has_referrals": True,
        "can_prev": page > 0,
        "can_next": page < total_pages - 1,
    }


async def page_prev(c, w, m: DialogManager):
    m.dialog_data["page"] -= 1
    await c.answer()


async def page_next(c, w, m: DialogManager):
    m.dialog_data["page"] += 1
    await c.answer()


referrals_dialog = Dialog(
    Window(
        Format("{referrals_text}"),
        Format("📄 <b>{page_str}</b>", when="has_referrals"),
        Row(
            Button(Const("◀️"), id="prev", on_click=page_prev, when="can_prev"),
            Button(Const("▶️"), id="next", on_click=page_next, when="can_next"),
        ),
        Button(
            Const("⬅️ В профиль"),
            id="back_profile",
            on_click=lambda c, w, m: m.start(
                ProfileSG.main,
                mode=StartMode.RESET_STACK,
            ),
        ),
        getter=referrals_getter,
        state=ReferralsSG.main,
    ),
)
