import inspect
from pathlib import Path
from typing import Protocol
from loguru import logger
from telegram.sender_sync import send_service_tg_message


DEFAULT_LOG_DIR = Path(__file__).resolve().parent.parent / 'log'
LOG_ROTATION = '1 month'
LOG_RETENTION = '1 year'
LOG_FORMAT = '{time:YYYY-MM-DD at HH:mm:ss.SSS} | {level} | {message}'
SHORT_LOG_FORMAT = '{time:YYYY-MM-DD at HH:mm:ss.SSS} | {level} | {extra[short_message]}\n'


class RichLogger(Protocol):
    def print_log(self, text: str) -> None: ...


def get_caller_log_name() -> str:
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back else None
    try:
        if caller is None:
            return 'app'
        return Path(caller.f_code.co_filename).stem
    finally:
        del frame


def short_log_formatter(cut_after: str | None):
    def formatter(record) -> str:
        message = record['message']
        if cut_after is not None:
            message = message.split(cut_after, maxsplit=1)[0]
        record['extra']['short_message'] = message
        return SHORT_LOG_FORMAT

    return formatter


def logger_init(
    log_dir: Path = DEFAULT_LOG_DIR,
    rich_log: RichLogger | None = None,
    log_name: str | None = None,
    rich_log_colorize: bool = True,
    log_cut_after: str | None = None,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_name = log_name or get_caller_log_name()

    if rich_log is not None:
        logger.remove()
        logger.add(
            sink=lambda msg: rich_log.print_log(str(msg).rstrip()),
            format=short_log_formatter(log_cut_after),
            level='INFO',
            colorize=rich_log_colorize,
        )
    logger.add(
        sink=log_dir / f'{log_name}.log',
        format=short_log_formatter(log_cut_after),
        level='INFO',
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression='zip',
        encoding='utf-8',
    )
    logger.add(
        sink=log_dir / f'{log_name}_debug.log',
        format=LOG_FORMAT,
        level='DEBUG',
        backtrace=True,
        diagnose=True,
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression='zip',
        encoding='utf-8',
    )
    logger.add(
        sink=lambda msg: send_service_tg_message(msg),
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='ERROR',
    )
