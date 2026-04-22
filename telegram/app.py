from pathlib import Path
from aiogram import Dispatcher
from loguru import logger
from telegram.bot import close_bot_session, orders_bot
from telegram.handlers import router
from telegram.sender_sync import send_service_tg_message


def init_logger() -> None:
    logger.add(
        sink=f'log/{Path(__file__).stem}.log',
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='INFO',
        backtrace=True,
        diagnose=True,
    )
    logger.add(
        sink=lambda msg: send_service_tg_message(msg),
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='ERROR',
    )


async def run_bot() -> None:
    init_logger()
    try:
        dp = Dispatcher()
        dp.include_router(router)
        await dp.start_polling(orders_bot)
    except Exception as e:
        logger.exception(f'Error in {__file__}: {e}')
    finally:
        await close_bot_session()
