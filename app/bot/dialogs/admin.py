from __future__ import annotations

import io
from datetime import timedelta, timezone, datetime
from math import ceil
from pathlib import Path

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, BufferedInputFile, Message
from aiogram_dialog import Dialog, Window, DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Column, Row
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.input import TextInput, MessageInput

from app.bot.dialogs.states import AdminSG, MainMenuSG
from app.core.settings import settings
from app.repository.admin import (
    export_users_to_excel,
    export_users_tasks_to_excel,
    get_user_tasks_page,
    export_single_user_tasks_to_excel,
    set_user_blocked,
)
from app.repository.admin_report import import_tasks_from_excel

EKB_TZ = timezone(timedelta(hours=5))

PAGE_SIZE = 5


async def open_import_tasks(c: CallbackQuery, w: Button, m: DialogManager):
    await m.start(AdminSG.import_tasks, mode=StartMode.RESET_STACK)


TEMPLATE_PATH = Path("app/static/template.xlsx")


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
        await c.answer()  # ничего не делаем
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
    now = datetime.now(EKB_TZ)
    date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
    buffer = await export_users_tasks_to_excel(date_from=date_from)
    await c.bot.send_document(
        chat_id=c.from_user.id,
        document=BufferedInputFile(buffer.read(), filename="users_tasks_today.xlsx"),
        caption="📊 Задания за сегодня",
    )
    await c.answer("Готово")


async def export_tasks_week(c: CallbackQuery, w, m: DialogManager):
    now = datetime.now(EKB_TZ)
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
                it.submitted_at.astimezone(EKB_TZ).strftime("%Y-%m-%d %H:%M")
                if it.submitted_at
                else "—"
            )
            processed = (
                it.processed_at.astimezone(EKB_TZ).strftime("%Y-%m-%d %H:%M")
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


async def back_to_admin_main(c: CallbackQuery, w, m: DialogManager):
    await m.start(AdminSG.main, mode=StartMode.RESET_STACK)


admin_dialog = Dialog(
    # MAIN WINDOW
    Window(
        Const("🛠 <b>Админ-панель</b>\n\nВыберите действие:"),
        Column(
            Row(
                Button(
                    Const("📊 Сегодня"),
                    id="tasks_today",
                    on_click=export_tasks_today,
                ),
                Button(
                    Const("📊 Неделя"),
                    id="tasks_week",
                    on_click=export_tasks_week,
                ),
            ),
            Row(
                Button(
                    Const("📊 Все задания"),
                    id="tasks_all",
                    on_click=export_tasks_all,
                ),
            ),
        ),
        Column(
            Button(
                Const("📄 Экспорт пользователей"),
                id="export_users",
                on_click=export_users,
            ),
            Button(
                Const("📈 Действия с пользователем"),
                id="user_stats",
                on_click=open_user_stats_lookup,
            ),
        ),
        Button(
            Const("📥 Импорт заданий (Excel)"),
            id="import_tasks",
            on_click=open_import_tasks,
        ),
        Column(
            Button(
                Const("⬅️ В меню"),
                id="menu",
                on_click=back_to_menu,
            ),
        ),
        state=AdminSG.main,
    ),
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
            Button(Const("⬅️ Назад"), id="back_admin", on_click=back_to_admin_main),
        ),
        state=AdminSG.user_lookup,
    ),
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
                Const("⬅️ Назад в админку"), id="back_main", on_click=back_to_admin_main
            ),
        ),
        getter=user_tasks_getter,
        state=AdminSG.user_tasks,
        disable_web_page_preview=True,
    ),
    Window(
        Const(
            "📥 <b>Импорт заданий из Excel</b>\n\n"
            "📄 <b>Формат Excel-файла</b>\n\n"
            "1️⃣ <b>Текст отзыва</b>\n"
            "• Текст, который пользователь должен написать в отзыве\n"
            "• Будет сохранён как <i>пример текста</i>\n"
            "• Обязательное поле\n\n"
            "2️⃣ <b>Город</b>\n"
            "• Название города <b>строго как в системе</b>\n"
            "• Можно оставить пустым — тогда задание подойдёт для любого города\n"
            "• Примеры: <code>Москва</code>, <code>Екатеринбург</code>, <code>Тюмень</code>\n\n"
            "3️⃣ <b>Пол</b>\n"
            "• Допустимые значения:\n"
            "  – <code>m</code>, <code>м</code>, <code>male</code>, <code>мужской</code>\n"
            "  – <code>f</code>, <code>ж</code>, <code>female</code>, <code>женский</code>\n"
            "  – <code>н/а</code>, пусто — без ограничения по полу\n\n"
            "4️⃣ <b>Ссылка на отзыв</b>\n"
            "• Прямая ссылка, где пользователь должен оставить отзыв\n"
            "• Обязательное поле\n\n"
            "⚠️ <b>Важно</b>\n"
            "• Если <b>хотя бы в одной строке</b> есть ошибка —\n"
            "  <b>ни одно задание создано не будет</b>\n"
            "• Все ошибки будут показаны после загрузки файла\n\n"
            "⬆️ Отправь Excel-файл или нажми «Назад»."
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
                id="back_admin",
                on_click=back_to_admin_main,
            ),
        ),
        state=AdminSG.import_tasks,
    ),
)
