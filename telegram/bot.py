from aiogram import Bot
from constants import tg_token_orders

orders_bot = Bot(token=tg_token_orders)


async def close_bot_session():
    if hasattr(orders_bot, 'session') and orders_bot.session:
        await orders_bot.session.close()
