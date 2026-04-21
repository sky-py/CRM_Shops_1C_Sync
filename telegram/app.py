from aiogram import Dispatcher
from telegram.bot import close_bot_session, orders_bot
from telegram.handlers import router


async def run_polling() -> None:
    dp = Dispatcher()
    dp.include_router(router)
    try:
        await dp.start_polling(orders_bot)
    finally:
        await close_bot_session()
