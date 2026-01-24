import logging


def setup_logging() -> None:
    """Настраивает базовое логирование приложения."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    logging.getLogger("apscheduler").setLevel(logging.INFO)