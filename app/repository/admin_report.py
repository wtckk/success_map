import io
import uuid
import logging
import pandas as pd
from sqlalchemy import select

from urllib.parse import urlparse

from sqlalchemy.exc import SQLAlchemyError, IntegrityError, DataError

from app.db.session import connection
from app.models import Task
from app.models.city import City

logger = logging.getLogger(__name__)


class ImportRowError(Exception):
    pass


class UnknownSourceError(ImportRowError):
    pass


def parse_source_and_text(link: str) -> tuple[str, str]:
    """
    Возвращает (source, text)
    """
    parsed = urlparse(link)
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    google_domains = {
        "google.com",
        "maps.google.com",
        "goo.gl",
        "maps.app.goo.gl",
    }

    if any(domain in netloc for domain in google_domains):
        return "Google Maps", "Оставить отзыв в Google Maps"

    yandex_domains = {
        "yandex.ru",
        "yandex.com",
        "maps.yandex.ru",
    }

    if any(domain in netloc for domain in yandex_domains):
        return "Яндекс Карты", "Оставить отзыв на Яндекс Картах"

    if "2gis" in netloc:
        return "2ГИС", "Оставить отзыв в 2ГИС"

    raise UnknownSourceError(f"Неизвестный источник ссылки: {link}")


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
    - логируются ошибки SQLAlchemy и неожиданные исключения
    """

    logger.info("Начат импорт задач из Excel")

    try:
        df = pd.read_excel(buffer)
        logger.info("Excel успешно прочитан. Найдено строк: %s", len(df))
    except Exception as e:
        logger.exception("Ошибка чтения Excel")
        return 0, [f"Ошибка чтения Excel: {str(e)}"]

    REQUIRED_COLUMNS = {
        "Текст отзыва",
        "Город",
        "Пол",
        "Ссылка на отзыв",
    }

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        logger.error("В Excel отсутствуют обязательные колонки: %s", missing)
        return 0, [f"В Excel отсутствуют колонки: {', '.join(missing)}"]

    errors: list[str] = []
    tasks_to_create: list[Task] = []

    try:
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
                source, task_text = parse_source_and_text(str(link).strip())
            except (ImportRowError, UnknownSourceError) as e:
                row_errors.append(str(e))
                gender = None
                source = None
                task_text = None

            city_id = None
            if not pd.isna(city_name):
                city_name_clean = str(city_name).strip()
                if city_name_clean.lower() not in ("н/а", "na", "none"):
                    stmt = select(City).where(City.name == city_name_clean)
                    try:
                        city = (await session.execute(stmt)).scalar_one_or_none()
                    except SQLAlchemyError:
                        logger.exception(
                            "Ошибка БД при поиске города. Строка %s", row_num
                        )
                        raise

                    if not city:
                        row_errors.append(f"Город не найден: {city_name_clean}")
                    else:
                        city_id = city.id

            if row_errors:
                logger.warning(
                    "Ошибки в строке %s: %s",
                    row_num,
                    "; ".join(row_errors),
                )
                errors.append(f"Строка {row_num}: " + "; ".join(row_errors))
                continue

            tasks_to_create.append(
                Task(
                    id=uuid.uuid4(),
                    text=task_text,
                    example_text=str(text_example).strip(),
                    link=str(link).strip(),
                    source=source,
                    required_gender=gender,
                    city_id=city_id,
                )
            )

        if errors:
            logger.warning(
                "Импорт прерван. Найдено %s ошибок. Выполняется rollback.",
                len(errors),
            )
            await session.rollback()
            return 0, errors

        session.add_all(tasks_to_create)

        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            logger.error("IntegrityError при commit: %s", str(e.orig))
            return 0, [f"Ошибка целостности данных: {str(e.orig)}"]

        except DataError as e:
            await session.rollback()
            logger.error("DataError при commit: %s", str(e.orig))
            return 0, [f"Ошибка формата данных: {str(e.orig)}"]

        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Общая ошибка SQLAlchemy при commit")
            return 0, ["Ошибка базы данных при сохранении"]

        logger.info(
            "Импорт успешно завершён. Создано задач: %s",
            len(tasks_to_create),
        )

        return len(tasks_to_create), []

    except Exception:
        await session.rollback()
        logger.exception("Критическая ошибка во время импорта")
        return 0, ["Критическая ошибка импорта. Проверьте логи сервера."]

