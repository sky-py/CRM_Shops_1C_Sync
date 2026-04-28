import asyncio
from contextlib import suppress
from pathlib import Path
from aiogram import Dispatcher
from loguru import logger
from telegram.bot import close_bot_session, orders_bot
from telegram.handlers import router
from telegram.sender_sync import send_service_tg_message


reload_file = Path(__file__).parent.parent / 'start_orders_bot.reload'


def init_logger() -> None:
    logger.add(
        sink=f'log/{Path(__file__).stem}.log',
        format='{time:YYYY-MM-DD at HH:mm:ss.SSS} | {level} | {message}',
        level='INFO',
        backtrace=True,
        diagnose=True,
    )
    logger.add(
        sink=lambda msg: send_service_tg_message(msg),
        format='{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}',
        level='ERROR',
    )


async def reload_file_watcher(dp: Dispatcher) -> None:
    while True:
        if reload_file.exists():
            logger.info(f'Found reload file {__file__}, STOPPING orders bot')
            await dp.stop_polling()
            return
        await asyncio.sleep(2)


async def run_bot() -> None:
    init_logger()
    logger.info(f'STARTING {__file__}')
    watcher_task = None
    try:
        dp = Dispatcher()
        dp.include_router(router)
        watcher_task = asyncio.create_task(reload_file_watcher(dp))
        await dp.start_polling(orders_bot)
    except Exception as e:
        logger.exception(f'Error in {__file__}: {e}')
    finally:
        if watcher_task is not None:
            watcher_task.cancel()
            with suppress(asyncio.CancelledError):
                await watcher_task
        await close_bot_session()
        reload_file.unlink(missing_ok=True)
        logger.info(f'SHUTTING DOWN {__file__}')
