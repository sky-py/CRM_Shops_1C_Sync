import asyncio
from contextlib import suppress
from pathlib import Path
from aiogram import Dispatcher
from config.logging import logger_init
from loguru import logger
from telegram.bot import close_bot_session, orders_bot
from telegram.handlers import router


reload_file = Path(__file__).parent.parent / 'start_orders_bot.reload'


async def reload_file_watcher(dp: Dispatcher) -> None:
    while True:
        if reload_file.exists():
            logger.info(f'Found reload file {__file__}, STOPPING orders bot')
            await dp.stop_polling()
            return
        await asyncio.sleep(2)


async def run_bot() -> None:
    logger_init()
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
