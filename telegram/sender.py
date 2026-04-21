import asyncio
from typing import Iterable
import constants
from aiogram.types import InlineKeyboardMarkup
from aiogram import Bot
from loguru import logger
from telegram.bot import orders_bot
from telegram.keyboards import build_claim_keyboard
from telegram.types import Notification


FIRST_MANAGER = 0


async def _send_tg_message_async(
    text: str, users: Iterable[int], reply_markup: InlineKeyboardMarkup | None = None,
    bot: Bot | None = None,
) -> None:
    text = text[:constants.TG_MAX_MESSAGE_LENGTH]
    if not constants.DO_SEND_TO_BOT:
        print('===TEST=== ', text)
        return

    bot = bot or orders_bot
    for user_id in users:
        try:
            await bot.send_message(user_id, text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f'Error sending message to {user_id}: {e}')


def send_tg_message(
    text: str, users: Iterable[int], reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Sync context: создаём локального бота, живёт только внутри этого вызова
        async def _run():
            bot = Bot(token=constants.tg_token_orders)
            try:
                await _send_tg_message_async(text=text, users=users, reply_markup=reply_markup, bot=bot)
            finally:
                await bot.session.close()
        asyncio.run(_run())
    else:
        # Async context: глобальный бот, loop уже есть
        task = loop.create_task(
            _send_tg_message_async(text=text, users=users, reply_markup=reply_markup)
        )
        task.add_done_callback(_handle_background_task_result)


def _handle_background_task_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception as exc:
        logger.exception(f'Error sending notification: {exc}')


def send_tg_message_to_managers(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    global FIRST_MANAGER
    managers = list(constants.managers.keys())
    managers = managers[FIRST_MANAGER:] + managers[:FIRST_MANAGER]
    FIRST_MANAGER += 1
    if FIRST_MANAGER >= len(managers):
        FIRST_MANAGER = 0
    send_tg_message(text=text, users=constants.managers | constants.additional_receivers, reply_markup=reply_markup)


def send_notification(notification: Notification) -> None:
    keyboard = None
    if notification.button:
        keyboard = build_claim_keyboard(
            source=notification.source, order_id=notification.order_id, shop_name=notification.shop_name
        )
    send_tg_message_to_managers(text=notification.text, reply_markup=keyboard)
