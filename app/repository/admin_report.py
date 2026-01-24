import io
import uuid
import logging
import pandas as pd
from sqlalchemy import select

from app.db.session import connection
from app.models import Task
from app.models.city import City

logger = logging.getLogger(__name__)


class ImportRowError(Exception):
    pass


def parse_gender(value) -> str | None:
    if value is None or pd.isna(value):
        return None

    v = str(value).strip().lower()

    if v in ("m", "м", "male", "муж", "мужской"):
        return "M"
    if v in ("f", "ж", "female", "жен", "женский"):
        return "F"
    if v in ("н/а", "na", "none", "-", ""):
        return None

    raise ImportRowError(f"Неизвестный пол: {value}")


@connection()
async def import_tasks_from_excel(
    *,
    session,
    buffer: io.BytesIO,
) -> tuple[int, list[str]]:
    """
    Атомарный импорт:
    - если есть ХОТЯ БЫ ОДНА ошибка → ничего не создаём
    - в одной строке может быть НЕСКОЛЬКО ошибок
    """
    df = pd.read_excel(buffer)

    REQUIRED_COLUMNS = {
        "Текст отзыва",
        "Город",
        "Пол",
        "Ссылка на отзыв",
    }

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        return 0, [f"В Excel отсутствуют колонки: {', '.join(missing)}"]

    errors: list[str] = []
    tasks_to_create: list[Task] = []

    for idx, row in df.iterrows():
        row_num = idx + 2
        row_errors: list[str] = []

        text_example = row["Текст отзыва"]
        city_name = row["Город"]
        gender_raw = row["Пол"]
        link = row["Ссылка на отзыв"]

        if pd.isna(text_example) or not str(text_example).strip():
            row_errors.append("Пустой текст отзыва")

        if pd.isna(link) or not str(link).strip():
            row_errors.append("Пустая ссылка на отзыв")

        try:
            gender = parse_gender(gender_raw)
        except ImportRowError as e:
            row_errors.append(str(e))
            gender = None

        city_id = None
        if not pd.isna(city_name):
            city_name_clean = str(city_name).strip()
            if city_name_clean.lower() not in ("н/а", "na", "none"):
                stmt = select(City).where(City.name == city_name_clean)
                city = (await session.execute(stmt)).scalar_one_or_none()
                if not city:
                    row_errors.append(f"Город не найден: {city_name_clean}")
                else:
                    city_id = city.id

        if row_errors:
            errors.append(f"Строка {row_num}: " + "; ".join(row_errors))
            continue

        tasks_to_create.append(
            Task(
                id=uuid.uuid4(),
                text="Оставить отзыв",
                example_text=str(text_example).strip(),
                link=str(link).strip(),
                required_gender=gender,
                city_id=city_id,
            )
        )

    if errors:
        await session.rollback()
        return 0, errors

    for task in tasks_to_create:
        session.add(task)

    await session.commit()
    return len(tasks_to_create), []
