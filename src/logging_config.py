import logging

from src.config import settings


def setup_logging(level: str | None = None) -> None:
    """初始化项目日志格式与级别。"""

    log_level = (level or settings.log_level).upper()

    logging.basicConfig(
        level=log_level,
        format=settings.log_format,
        force=True,
    )

    for noisy_logger in ("httpx", "chromadb", "uvicorn.access"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
