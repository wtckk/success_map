import io
import statistics
from datetime import timedelta, timezone, datetime
from html import escape
from math import ceil
from pathlib import Path

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, BufferedInputFile, Message
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Column, Row
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.input import TextInput, MessageInput


from app.bot.dialogs.states import AdminSG, MainMenuSG
from app.bot.utils.tg import get_source_emoji_html
from app.core.settings import settings
from app.repository.admin import (
    export_users_to_excel,
    export_users_tasks_to_excel,
    get_user_tasks_page,
    export_single_user_tasks_to_excel,
    set_user_blocked,
    get_daily_completed_stats,
    get_top_5_users,
    export_available_tasks_to_excel,
    get_users_statistics,
    get_user_weekly_approved_count,
)
from app.repository.admin_report import import_tasks_from_excel
from app.repository.task import get_tasks_statistics, get_assigned_tasks_page

MSC_TZ = timezone(timedelta(hours=3))

PAGE_SIZE = 5

TEMPLATE_PATH = Path("app/static/template.xlsx")


def format_duration(delta: timedelta) -> str:
    total_minutes = int(delta.total_seconds() // 60)

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours:
        return f"{hours}ч"
    return f"{minutes}м"



async def open_import_tasks(c: CallbackQuery, w: Button, m: DialogManager):
    await m.start(AdminSG.import_tasks, mode=StartMode.RESET_STACK)


def format_minutes(value: float) -> str:
    if not value:
        return "—"
    hours = int(value // 60)
    minutes = int(value % 60)

    if hours:
        return f"{hours}ч {minutes}м"
    return f"{minutes}м"


async def assigned_tasks_getter(dialog_manager: DialogManager, **kwargs):
    page = int(dialog_manager.dialog_data.get("page", 0))

    total_count, items = await get_assigned_tasks_page(
        page=page,
        page_size=PAGE_SIZE,
    )

    total_pages = max(1, ceil(total_count / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    dialog_manager.dialog_data["page"] = page
    dialog_manager.dialog_data["last_page"] = total_pages - 1

    if total_count == 0:
        return {
            "assigned_text": "📭 Сейчас нет выданных заданий.",
            "page_str": "—",
            "assigned_count": 0,
        }

    sections = []

    now = datetime.now(MSC_TZ)
    start_num = page * PAGE_SIZE + 1

    for i, assignment in enumerate(items, start=start_num):
        task = assignment.task
        user = assignment.user

        created_at_msc = assignment.created_at.astimezone(MSC_TZ)

        delta = now - created_at_msc
        duration = format_duration(delta)

        persona_map = {
            "M": "👨 Мужское",
            "F": "👩 Женское",
            None: "🧑 Не важно",
        }

        persona_label = persona_map.get(task.required_gender, "Не указано")

        example_block = (
            f"\n\n✍️ <b>Текст отзыва:</b>\n<pre>{escape(task.example_text)}</pre>"
            if task.example_text
            else ""
        )

        source_emoji = get_source_emoji_html(task.source)

        full_name = user.full_name or "—"
        username = f"@{user.username}" if user.username else ""
        tg_id = user.tg_id

        user_block = (
            f"👤 <b>Исполнитель:</b> "
            f"{escape(full_name)} "
            f"{escape(f'({username})' if username else '')}\n"
            f"🆔 <code>{tg_id}</code>\n"
        )

        section = (
            f"📌 <b>#{i}</b>  ⏱ <b>{duration}</b>\n"
            f"{source_emoji} <code>{task.human_code}</code>"
            f"{example_block}\n\n"
            f"{user_block}"
            f"👥 <b>От какого лица:</b> {persona_label}\n"
            f"🔗 <a href='{escape(task.link)}'>Перейти</a>"
        )

        sections.append(section)

    return {
        "assigned_text": "\n\n━━━━━━━━━━━━━━\n\n".join(sections),
        "page_str": f"{page + 1}/{total_pages}",
        "assigned_count": total_count,
    }


async def global_stats_getter(dialog_manager: DialogManager, **kwargs):
    stats = await get_tasks_statistics()

    total_assignments = stats["total_assignments"] or 1
    approved_users = stats["approved_users"] or 1

    approved_percent = round(stats["approved"] / total_assignments * 100)
    rejected_percent = round(stats["rejected"] / total_assignments * 100)
    in_progress_percent = round(stats["in_progress"] / total_assignments * 100)

    avg_per_user = round(stats["approved"] / approved_users, 2)

    formatted_exec_time = format_minutes(stats["avg_execution_minutes"])

    users_stats = await get_users_statistics()

    return {
        "total_tasks": stats["total_tasks"],
        "free_tasks": stats["free_tasks"],
        "total_assignments": stats["total_assignments"],
        "approved": stats["approved"],
        "approved_percent": approved_percent,
        "rejected": stats["rejected"],
        "rejected_percent": rejected_percent,
        "in_progress": stats["in_progress"],
        "in_progress_percent": in_progress_percent,
        "approved_users": stats["approved_users"],
        "avg_per_user": avg_per_user,
        "avg_execution_time": formatted_exec_time,
        "total_users": users_stats["total_users"],
        "new_today": users_stats["new_today"],
        "new_week": users_stats["new_week"],
        "new_month": users_stats["new_month"],
    }


async def open_global_stats(c: CallbackQuery, w: Button, m: DialogManager):
    await m.start(AdminSG.analytics, mode=StartMode.NORMAL)


async def download_import_template(
    c: CallbackQuery,
    w: Button,
    m: DialogManager,
):
    if c.from_user.id not in settings.admin_id_list:
        await c.answer("⛔ Доступ запрещён", show_alert=True)
        return

    if not TEMPLATE_PATH.exists():
        await c.answer("❌ Шаблон не найден", show_alert=True)
        return

    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(
            TEMPLATE_PATH.read_bytes(),
            filename="template_tasks_import.xlsx",
        ),
        caption="📄 <b>Шаблон Excel для импорта заданий</b>",
    )

    await c.answer("Готово")


async def on_excel_uploaded(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
):
    if message.from_user.id not in settings.admin_id_list:
        await message.answer("⛔ <b>Доступ запрещён</b>")
        return

    document = message.document
    if not document or not document.file_name.endswith(".xlsx"):
        await message.answer(
            "❌ <b>Неверный файл</b>\n\nПришли Excel-файл в формате <code>.xlsx</code>."
        )
        return

    file = await message.bot.download(document)

    created, errors = await import_tasks_from_excel(buffer=file)

    if errors:
        preview_errors = errors[:20]

        text = (
            "❌ <b>Импорт не выполнен</b>\n\n"
            "🚫 <b>Ни одно задание не создано</b>, так как в файле есть ошибки.\n\n"
            "🔎 <b>Ошибки:</b>\n" + "\n".join(f"• {e}" for e in preview_errors)
        )

        await message.answer(text)

        if len(errors) > 20:
            txt_content = "\n".join(errors)
            txt_file = io.BytesIO(txt_content.encode("utf-8"))
            txt_file.seek(0)

            await message.bot.send_document(
                chat_id=message.from_user.id,
                document=BufferedInputFile(
                    txt_file.read(),
                    filename="import_errors.txt",
                ),
                caption=(
                    f"📄 <b>Полный список ошибок импорта</b>\n"
                    f"Всего ошибок: <b>{len(errors)}</b>"
                ),
            )

        await dialog_manager.start(AdminSG.main, mode=StartMode.RESET_STACK)
        return

    text = (
        "✅ <b>Импорт успешно завершён</b>\n\n"
        f"📦 Создано заданий: <b>{created}</b>\n\n"
        "Ты вернулся в админ-панель."
    )

    await message.answer(text)

    await dialog_manager.start(AdminSG.main, mode=StartMode.RESET_STACK)


async def block_user(c: CallbackQuery, w: Button, m: DialogManager):
    tg_id = m.dialog_data.get("tg_id")
    if not tg_id:
        await c.answer("Пользователь не найден", show_alert=True)
        return

    if tg_id in settings.admin_id_list:
        await c.answer("⛔ Администраторов блокировать нельзя", show_alert=True)
        return

    await set_user_blocked(tg_id=int(tg_id), blocked=True)
    await c.answer("🚫 Пользователь заблокирован")


async def unblock_user(c: CallbackQuery, w: Button, m: DialogManager):
    tg_id = m.dialog_data.get("tg_id")
    if not tg_id:
        await c.answer("Пользователь не найден", show_alert=True)
        return

    if tg_id in settings.admin_id_list:
        await c.answer("⛔ Администраторов блокировать нельзя", show_alert=True)
        return

    await set_user_blocked(tg_id=int(tg_id), blocked=False)
    await c.answer("🔓 Пользователь разблокирован")


async def page_first(c: CallbackQuery, w: Button, m: DialogManager):
    if m.dialog_data.get("page", 0) <= 0:
        await c.answer()
        return

    m.dialog_data["page"] = 0
    await c.answer()


async def page_last(c: CallbackQuery, w: Button, m: DialogManager):
    page = int(m.dialog_data.get("page", 0))
    last_page = m.dialog_data.get("last_page", 0)

    if page >= last_page:
        await c.answer()
        return

    m.dialog_data["page"] = last_page
    await c.answer()


def is_admin(data: dict, widget, manager: DialogManager) -> bool:
    user = manager.event.from_user
    return user.id in settings.admin_id_list


async def go_to_admin_panel(c: CallbackQuery, w, m: DialogManager):
    if c.from_user.id not in settings.admin_id_list:
        await c.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await m.start(AdminSG.main, mode=StartMode.RESET_STACK)


async def back_to_menu(c: CallbackQuery, w, m: DialogManager):
    await m.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


async def export_users(c: CallbackQuery, w: Button, m: DialogManager):
    buffer = await export_users_to_excel()
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename="users.xlsx"),
        caption="📄 Экспорт всех пользователей",
    )
    await c.answer("Готово")


async def export_tasks_today(c: CallbackQuery, w, m: DialogManager):
    now = datetime.now(MSC_TZ)
    date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
    buffer = await export_users_tasks_to_excel(date_from=date_from)
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename="users_tasks_today.xlsx"),
        caption="📊 Задания за сегодня",
    )
    await c.answer("Готово")


async def export_tasks_week(c: CallbackQuery, w, m: DialogManager):
    now = datetime.now(MSC_TZ)
    date_from = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    buffer = await export_users_tasks_to_excel(date_from=date_from)
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename="users_tasks_week.xlsx"),
        caption="📊 Задания за текущую неделю",
    )
    await c.answer("Готово")


async def export_tasks_all(c: CallbackQuery, w, m: DialogManager):
    buffer = await export_users_tasks_to_excel()
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename="users_tasks_all.xlsx"),
        caption="📊 Все задания пользователей",
    )
    await c.answer("Готово")


def _period_title(period: str) -> str:
    return {"day": "Сегодня", "week": "Неделя", "all": "Всё время"}.get(period, "—")


async def open_user_stats_lookup(c: CallbackQuery, w: Button, m: DialogManager):
    m.dialog_data.pop("tg_id", None)
    m.dialog_data["period"] = "all"
    m.dialog_data["page"] = 0
    await m.start(AdminSG.user_lookup, mode=StartMode.RESET_STACK)


def _parse_tg_id(value: str) -> int | None:
    value = value.strip().replace("@", "")
    if not value.isdigit():
        return None
    try:
        return int(value)
    except Exception:
        return None


async def on_tg_id_input(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    value: str,
):
    value = value.strip().replace("@", "")
    if not value.isdigit():
        await message.answer(
            "❌ Некорректный ввод.\n\n"
            "Введите <b>числовой</b> Telegram ID.\n"
            "Пример: <code>123456789</code>"
        )
        return

    tg_id = int(value)

    manager.dialog_data["tg_id"] = tg_id
    manager.dialog_data["period"] = "all"
    manager.dialog_data["page"] = 0

    await manager.switch_to(AdminSG.user_tasks)


async def user_tasks_getter(dialog_manager: DialogManager, **kwargs):
    tg_id = dialog_manager.dialog_data.get("tg_id")
    period = dialog_manager.dialog_data.get("period", "all")
    page = int(dialog_manager.dialog_data.get("page", 0))

    base_ctx = {
        "is_blocked": False,
        "block_status": "—",
        "block_button_text": "—",
        "has_user": False,
        "error": "",
        "tg_id": tg_id or "—",
        "username": "—",
        "full_name": "—",
        "phone": "—",
        "gender": "—",
        "city": "—",
        "referrer": "—",
        "period_title": _period_title(period),
        "total_count": 0,
        "page_str": "—",
        "tasks_text": "",
        "can_prev": False,
        "can_next": False,
    }

    if not tg_id:
        base_ctx["error"] = "Не указан tg_id."
        return base_ctx

    user, total_count, items = await get_user_tasks_page(
        tg_id=int(tg_id),
        period=period,
        page=page,
        page_size=PAGE_SIZE,
    )

    if not user:
        base_ctx["error"] = f"Пользователь с tg_id={tg_id} не найден."
        return base_ctx

    ref = (
        f"{user.referrer.full_name or '—'} ({user.referrer.tg_id})"
        if user.referrer
        else "—"
    )
    is_admin_user = user.tg_id in settings.admin_id_list

    is_blocked = user.is_blocked
    block_status = "🚫 Заблокирован" if is_blocked else "🟢 Активен"
    block_button_text = "🔓 Разблокировать" if is_blocked else "🚫 Заблокировать"

    total_pages = max(1, ceil(total_count / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    dialog_manager.dialog_data["page"] = page

    last_page = total_pages - 1
    dialog_manager.dialog_data["last_page"] = last_page

    if total_count == 0:
        tasks_text = (
            "Пока нет подходящих заданий по выбранному периоду.\n\n"
            "Попробуй изменить период."
        )
    else:
        lines = []
        start_num = page * PAGE_SIZE + 1

        for i, it in enumerate(items, start=start_num):
            submitted = (
                it.submitted_at.astimezone(MSC_TZ).strftime("%Y-%m-%d %H:%M")
                if it.submitted_at
                else "—"
            )
            processed = (
                it.processed_at.astimezone(MSC_TZ).strftime("%Y-%m-%d %H:%M")
                if it.processed_at
                else "—"
            )
            admin = it.processed_by_admin_id or "—"

            def cut(s: str | None, n: int = 400) -> str:
                if not s:
                    return "—"
                s = s.strip()
                return s if len(s) <= n else s[:n] + "…"

            lines.append(
                f"🧾 <b>Задание #{i}</b>\n"
                f"• Статус: <b>{it.status}</b>\n"
                f"• Отправлено: <b>{submitted}</b>\n"
                f"• Проверено: <b>{processed}</b>\n"
                f"• Админ: <b>{admin}</b>\n\n"
                f"<b>Текст:</b>\n{cut(it.task_text)}\n\n"
                f"<b>Пример:</b>\n{cut(it.task_example)}\n\n"
                f"<b>Ссылка:</b> {it.task_link or '—'}"
            )

        tasks_text = "\n━━━━━━━━━━━━━━\n".join(lines)

    return {
        "has_user": True,
        "error": "",
        "tg_id": user.tg_id,
        "username": f"@{user.username}" if user.username else "—",
        "full_name": user.full_name or "—",
        "phone": user.phone or "—",
        "gender": user.gender or "—",
        "city": user.city.name if user.city else "—",
        "referrer": ref,
        "period_title": _period_title(period),
        "total_count": total_count,
        "page_str": f"{page + 1}/{total_pages}",
        "tasks_text": tasks_text,
        "can_first": page > 0,
        "can_prev": page > 0,
        "can_next": page < last_page,
        "can_last": page < last_page,
        "is_blocked": is_blocked,
        "block_status": block_status,
        "block_button_text": block_button_text,
        "is_admin_user": is_admin_user,
        "can_block": not user.is_blocked,
        "can_unblock": user.is_blocked,
    }


async def set_period_day(c: CallbackQuery, w: Button, m: DialogManager):
    m.dialog_data["period"] = "day"
    m.dialog_data["page"] = 0
    await c.answer("Период: Сегодня")


async def set_period_week(c: CallbackQuery, w: Button, m: DialogManager):
    m.dialog_data["period"] = "week"
    m.dialog_data["page"] = 0
    await c.answer("Период: Неделя")


async def set_period_all(c: CallbackQuery, w: Button, m: DialogManager):
    m.dialog_data["period"] = "all"
    m.dialog_data["page"] = 0
    await c.answer("Период: Всё время")


async def page_prev(c: CallbackQuery, w: Button, m: DialogManager):
    page = int(m.dialog_data.get("page", 0))
    if page <= 0:
        await c.answer()
        return

    m.dialog_data["page"] = page - 1
    await c.answer()


async def page_next(c: CallbackQuery, w: Button, m: DialogManager):
    page = int(m.dialog_data.get("page", 0))
    last_page = m.dialog_data.get("last_page", 0)

    if page >= last_page:
        await c.answer()
        return

    m.dialog_data["page"] = page + 1
    await c.answer()


async def export_user_stats_excel(c: CallbackQuery, w: Button, m: DialogManager):
    tg_id = m.dialog_data.get("tg_id")
    period = m.dialog_data.get("period", "all")
    if not tg_id:
        await c.answer("Сначала укажи tg_id", show_alert=True)
        return

    buffer = await export_single_user_tasks_to_excel(tg_id=int(tg_id), period=period)

    filename = f"user_{tg_id}_tasks_{period}.xlsx"
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename=filename),
        caption=f"📤 Excel: задания пользователя <b>{tg_id}</b> — <b>{_period_title(period)}</b>",
    )
    await c.answer("Готово")


async def analytics_dynamics_getter(dialog_manager, **kwargs):
    data = await get_daily_completed_stats()

    if not data:
        return {"dynamics_text": "📊 Нет данных"}

    width = 10

    counts = [count for _, count in data]
    max_value = max(counts) or 1
    avg_value = statistics.mean(counts)

    scale = max_value if max_value <= avg_value * 2 else avg_value * 2
    if scale == 0:
        scale = 1

    max_digits = max(len(str(c)) for c in counts)

    max_day_len = max(len(str(day)) for day, _ in data)

    lines = ["📊 <b>Динамика выполненных заданий</b>\n"]

    prev = None

    for day, count in data:
        ratio = min(count / scale, 1)
        bar_len = round(ratio * width)

        if count > 0 and bar_len == 0:
            bar_len = 1

        bar = "▰" * bar_len + "▱" * (width - bar_len)

        if prev is None:
            trend = "➖"
        elif count > prev:
            trend = "📈"
        elif count < prev:
            trend = "📉"
        else:
            trend = "➖"

        prev = count

        day_str = f"{day:>{max_day_len}}"
        count_str = f"{count:>{max_digits}}"

        lines.append(f"{day_str}  {bar}  <b>{count_str}</b>  {trend}")

    return {"dynamics_text": "\n".join(lines)}


async def export_available_tasks(c: CallbackQuery, w: Button, m: DialogManager):
    buffer = await export_available_tasks_to_excel()

    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(
            buffer.read(),
            filename="available_tasks.xlsx",
        ),
        caption="📦 Доступные задания на текущий момент",
    )
    await c.answer("Готово")


async def analytics_top_getter(dialog_manager: DialogManager, **kwargs):
    users = await get_top_5_users()

    if not users:
        return {"top_text": "📊 Пока нет выполненных заданий"}

    stats = await get_tasks_statistics()
    total_approved = stats["approved"] or 1

    medals = [
        "<tg-emoji emoji-id='5188344996356448758'>🥇</tg-emoji>",
        "🥈",
        "🥉",
    ]

    max_count_width = max(len(str(u["count"])) for u in users)
    percents = [round(u["count"] / total_approved * 100) for u in users]
    max_percent_width = max(len(str(p)) for p in percents)

    lines = ["🏆 <b>Топ исполнителей</b>\n"]

    for i, user in enumerate(users):
        medal = medals[i] if i < 3 else f"{i + 1}."

        percent = percents[i]
        weekly = await get_user_weekly_approved_count(user_id=user["id"])

        trend = f"📈 +{weekly}" if weekly > 0 else "➖ 0"

        count_str = f"{user['count']:>{max_count_width}}"
        percent_str = f"{percent:>{max_percent_width}}"

        name = (user["name"] or "—").strip()
        username = f"@{user['username']}" if user["username"] else ""

        if i == 0:
            lines.append(
                f"{medal} <b>{name}</b> {username}\n"
                f"   📦 <b>{count_str}</b>  •  📊 {percent_str}%  •  {trend}"
            )
        else:
            lines.append(
                f"{medal} {name} {username}\n"
                f"   📦 <b>{count_str}</b>  •  📊 {percent_str}%  •  {trend}"
            )

    return {"top_text": "\n\n".join(lines)}


async def back_to_admin_main(c: CallbackQuery, w, m: DialogManager):
    await m.start(AdminSG.main, mode=StartMode.RESET_STACK)


admin_dialog = Dialog(
    # main menu
    Window(
        Const("🛠 <b>Админ-панель</b>\n\nВыберите раздел:"),
        Column(
            Button(
                Const("🧾 Отчёты"),
                id="go_reports",
                on_click=lambda c, w, m: m.start(AdminSG.reports),
            ),
            Button(
                Const("📊 Аналитика"),
                id="go_analytics",
                on_click=lambda c, w, m: m.start(AdminSG.analytics),
            ),
            Button(
                Const("👥 Пользователи"),
                id="go_users",
                on_click=lambda c, w, m: m.start(AdminSG.users),
            ),
            Button(
                Const("⚙️ Управление заданиями"),
                id="go_manage",
                on_click=lambda c, w, m: m.start(AdminSG.manage),
            ),
            Button(Const("⬅️ В меню"), id="menu", on_click=back_to_menu),
        ),
        state=AdminSG.main,
    ),
    # reports
    Window(
        Const("🧾 <b>Отчёты по заданиям</b>\n\nВыберите период:"),
        Column(
            Row(
                Button(
                    Const("📊 Сегодня"), id="tasks_today", on_click=export_tasks_today
                ),
                Button(Const("📊 Неделя"), id="tasks_week", on_click=export_tasks_week),
            ),
            Button(Const("📊 Всё время"), id="tasks_all", on_click=export_tasks_all),
        ),
        Row(
            Button(
                Const("⬅️ Назад"), id="back_main_reports", on_click=back_to_admin_main
            ),
        ),
        state=AdminSG.reports,
    ),
    # users section
    Window(
        Const("👥 <b>Пользователи</b>\n\nВыберите действие:"),
        Column(
            Button(
                Const("📄 Экспорт пользователей"),
                id="export_users",
                on_click=export_users,
            ),
            Button(
                Const("📈 Статистика пользователя"),
                id="user_stats",
                on_click=open_user_stats_lookup,
            ),
        ),
        Row(
            Button(Const("⬅️ Назад"), id="back_main_users", on_click=back_to_admin_main),
        ),
        state=AdminSG.users,
    ),
    # manage tasks
    Window(
        Const("⚙️ <b>Управление заданиями</b>\n\nВыберите действие:"),
        Column(
            Button(
                Const("📥 Импорт заданий"),
                id="import_tasks",
                on_click=open_import_tasks,
            ),
            Button(
                Const("📤 Экспорт доступных заданий"),
                id="export_available_tasks",
                on_click=export_available_tasks,
            ),
            Button(
                Const("📋 Выданные задания"),
                id="assigned_tasks",
                on_click=lambda c, w, m: m.start(
                    AdminSG.assigned_tasks,
                    mode=StartMode.NORMAL,
                ),
            ),
        ),
        Row(
            Button(
                Const("⬅️ Назад"), id="back_main_manage", on_click=back_to_admin_main
            ),
        ),
        state=AdminSG.manage,
    ),
    Window(
        Format(
            "📋 <b>Выданные задания</b>\n\n"
            "📦 Всего: <b>{assigned_count}</b>\n"
            "📄 Страница: <b>{page_str}</b>\n\n"
            "{assigned_text}"
        ),
        Row(
            Button(
                Const("🔄 Обновить"),
                id="refresh_assigned",
                on_click=lambda c, w, m: m.start(
                    AdminSG.assigned_tasks,
                    mode=StartMode.NORMAL,
                ),
            ),
            Button(
                Const("⬅️ Назад"),
                id="back_manage_from_assigned",
                on_click=lambda c, w, m: m.start(
                    AdminSG.manage,
                    mode=StartMode.NORMAL,
                ),
            ),
        ),
        Row(
            Button(Const("⏮️"), id="first_a", on_click=page_first),
            Button(Const("◀️"), id="prev_a", on_click=page_prev),
            Button(Const("▶️"), id="next_a", on_click=page_next),
            Button(Const("⏭️"), id="last_a", on_click=page_last),
        ),
        getter=assigned_tasks_getter,
        state=AdminSG.assigned_tasks,
        disable_web_page_preview=True,
    ),
    # analytics
    Window(
        Const("📊 <b>Аналитика</b>\n\nВыберите раздел:"),
        Column(
            Button(
                Const("📦 Общая статистика"),
                id="analytics_overview",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_overview),
            ),
            Button(
                Const("📈 Динамика (7 дней)"),
                id="analytics_dynamics",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_dynamics),
            ),
            Button(
                Const("🏆 Топ исполнителей"),
                id="analytics_top",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_top),
            ),
        ),
        Row(
            Button(
                Const("⬅️ Назад"), id="back_main_analytics", on_click=back_to_admin_main
            ),
        ),
        state=AdminSG.analytics,
    ),
    Window(
        Format(
            "📦 <b>ОБЩАЯ СТАТИСТИКА</b>\n\n"
            "📋 <b>Задания</b>\n"
            "   Всего: <b>{total_tasks}</b>\n"
            "   ├ 🟢 Доступно: <b>{free_tasks}</b>\n"
            "   ├ ⏳ В работе: <b>{in_progress}</b>  (<b>{in_progress_percent}%</b>)\n"
            "   ├ ✅ Выполнено: <b>{approved}</b>  (<b>{approved_percent}%</b>)\n"
            "   └ ❌ Отклонено: <b>{rejected}</b>  (<b>{rejected_percent}%</b>)\n\n"
            "👥 <b>Пользователи</b>\n"
            "   Всего: <b>{total_users}</b>\n"
            "   ├ Сегодня: <b>{new_today}</b>\n"
            "   ├ 7 дней: <b>{new_week}</b>\n"
            "   └ 30 дней: <b>{new_month}</b>\n\n"
            "👤 <b>Исполнители</b>\n"
            "   Активных: <b>{approved_users}</b>\n"
            "   └ Один исполнитель выполняет ~<b>{avg_per_user}</b> заданий\n\n"
            "⏱ <b>Эффективность</b>\n"
            "   └ Среднее время выполнения: <b>{avg_execution_time}</b>"
        ),
        Row(
            Button(
                Const("🔄 Обновить"),
                id="refresh_overview",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_overview),
            ),
            Button(
                Const("⬅️ Назад"),
                id="back_overview",
                on_click=lambda c, w, m: m.start(AdminSG.analytics),
            ),
        ),
        getter=global_stats_getter,
        state=AdminSG.analytics_overview,
    ),
    Window(
        Format("📈 <b>Динамика (7 дней)</b>\n\n<code>{dynamics_text}</code>"),
        Row(
            Button(
                Const("🔄 Обновить"),
                id="refresh_dyn",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_dynamics),
            ),
            Button(
                Const("⬅️ Назад"),
                id="back_dyn",
                on_click=lambda c, w, m: m.start(AdminSG.analytics),
            ),
        ),
        getter=analytics_dynamics_getter,
        state=AdminSG.analytics_dynamics,
    ),
    Window(
        Format("{top_text}"),
        Row(
            Button(
                Const("🔄 Обновить"),
                id="refresh_top",
                on_click=lambda c, w, m: m.start(AdminSG.analytics_top),
            ),
            Button(
                Const("⬅️ Назад"),
                id="back_top",
                on_click=lambda c, w, m: m.start(AdminSG.analytics),
            ),
        ),
        getter=analytics_top_getter,
        state=AdminSG.analytics_top,
    ),
    # user lookup
    Window(
        Const(
            "📈 <b>Информация о пользователе</b>\n\n"
            "Введи <b>tg_id</b> пользователя.\n"
            "Пример: <code>123456789</code>\n\n"
            "Чтобы отменить — нажми «Назад»."
        ),
        TextInput(
            id="tg_id_input",
            on_success=on_tg_id_input,
        ),
        Row(
            Button(
                Const("⬅️ Назад"), id="back_admin_lookup", on_click=back_to_admin_main
            ),
        ),
        state=AdminSG.user_lookup,
    ),
    # user tasks
    Window(
        Format(
            "📈 <b>Статистика пользователя</b>\n\n"
            "👤 <b>{full_name}</b> ({username})\n"
            "• tg_id: <code>{tg_id}</code>\n"
            "• Телефон: <b>{phone}</b>\n"
            "• Пол: <b>{gender}</b>\n"
            "• Город: <b>{city}</b>\n"
            "• Статус пользователя: <b>{block_status}</b>\n"
            "• Реферер: <b>{referrer}</b>\n\n"
            "🗓 Период: <b>{period_title}</b>\n"
            "📦 Всего заданий: <b>{total_count}</b>\n"
            "📄 Страница: <b>{page_str}</b>\n\n"
            "{tasks_text}"
        ),
        Row(
            Button(Const("Сегодня"), id="p_day", on_click=set_period_day),
            Button(Const("Неделя"), id="p_week", on_click=set_period_week),
            Button(Const("Всё время"), id="p_all", on_click=set_period_all),
        ),
        Row(
            Button(Const("⏮️"), id="first", on_click=page_first),
            Button(Const("◀️"), id="prev", on_click=page_prev),
            Button(Const("▶️"), id="next", on_click=page_next),
            Button(Const("⏭️"), id="last", on_click=page_last),
        ),
        Row(
            Button(
                Const("📤 Экспорт (Excel)"),
                id="export_one",
                on_click=export_user_stats_excel,
            ),
            Button(
                Const("🔍 Другой tg_id"),
                id="change_tg",
                on_click=open_user_stats_lookup,
            ),
        ),
        Row(
            Button(
                Const("🚫 Заблокировать"),
                id="block_user",
                on_click=block_user,
                when="can_block",
            ),
            Button(
                Const("🔓 Разблокировать"),
                id="unblock_user",
                on_click=unblock_user,
                when="can_unblock",
            ),
        ),
        Row(
            Button(
                Const("⬅️ Назад в админку"),
                id="back_main_user_tasks",
                on_click=back_to_admin_main,
            ),
        ),
        getter=user_tasks_getter,
        state=AdminSG.user_tasks,
        disable_web_page_preview=True,
    ),
    # import
    Window(
        Const(
            "📥 <b>Импорт заданий из Excel</b>\n\n"
            "Отправь Excel-файл в формате .xlsx\n"
            "Если в файле будет ошибка — ни одно задание создано не будет."
        ),
        MessageInput(
            on_excel_uploaded,
            content_types=[ContentType.DOCUMENT],
        ),
        Row(
            Button(
                Const("📄 Скачать шаблон"),
                id="download_template",
                on_click=download_import_template,
            ),
        ),
        Row(
            Button(
                Const("⬅️ Назад в админку"),
                id="back_admin_import",
                on_click=back_to_admin_main,
            ),
        ),
        state=AdminSG.import_tasks,
    ),
)
