import asyncio
from collections.abc import Iterable
from typing import Literal
import constants
from aiogram.types import InlineKeyboardMarkup
from loguru import logger
from telegram.bot import orders_bot
from telegram.keyboards import build_claim_keyboard
from telegram.types import Notification


FIRST_MANAGER = 0


async def _send_tg_message_to_user(user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        logger.debug(f'Sending message to {user_id}: {text}')
        await orders_bot.send_message(user_id, text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f'Error sending message to {user_id}: {e}')


async def send_tg_message(text: str, users: Iterable[int], reply_markup: InlineKeyboardMarkup | None = None) -> None:
    text = text[: constants.TG_MAX_MESSAGE_LENGTH]
    if not constants.DO_SEND_TO_BOT:
        print('===TEST=== ', text)
        return

    await asyncio.gather(*(_send_tg_message_to_user(user_id, text, reply_markup) for user_id in users))


async def send_tg_message_to_managers(
    text: str, reply_markup: InlineKeyboardMarkup | None = None, message_type: Literal['order', 'info'] = 'info'
) -> None:
    global FIRST_MANAGER
    additional_receivers = list(constants.additional_receivers.keys())
    managers = list(constants.managers.keys())
    if message_type == 'order':  # shifting managers
        managers = managers[FIRST_MANAGER:] + managers[:FIRST_MANAGER]
        FIRST_MANAGER += 1
        if FIRST_MANAGER >= len(managers):
            FIRST_MANAGER = 0
    await send_tg_message(text=text, users=managers, reply_markup=reply_markup)
    await send_tg_message(text=text, users=additional_receivers, reply_markup=reply_markup)


async def send_notification(notification: Notification) -> None:
    keyboard = None
    if notification.button:
        keyboard = build_claim_keyboard(
            source=notification.source,
            order_id=notification.order_id,
            source_uuid=notification.source_uuid,
            shop_name=notification.shop_name,
        )
    await send_tg_message_to_managers(text=notification.text, reply_markup=keyboard, message_type='order')
