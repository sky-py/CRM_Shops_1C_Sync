from typing import Iterable
import constants
from aiogram.types import InlineKeyboardMarkup
from loguru import logger
from telegram.bot import orders_bot
from telegram.keyboards import build_claim_keyboard
from telegram.types import Notification

FIRST_MANAGER = 0


async def send_tg_message(text: str, users: Iterable[int], reply_markup: InlineKeyboardMarkup | None = None) -> None:
    text = text[: constants.TG_MAX_MESSAGE_LENGTH]
    if not constants.DO_SEND_TO_BOT:
        print('===TEST=== ', text)
        return

    for user_id in users:
        try:
            await orders_bot.send_message(user_id, text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f'Error sending message to {user_id}: {e}')


async def send_tg_message_to_managers(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    global FIRST_MANAGER
    managers = list(constants.managers.keys())
    managers_sorted = managers[FIRST_MANAGER:] + managers[:FIRST_MANAGER]
    FIRST_MANAGER += 1
    if FIRST_MANAGER >= len(managers):
        FIRST_MANAGER = 0
    await send_tg_message(
        text=text, users=managers_sorted + list(constants.additional_receivers.keys()), reply_markup=reply_markup
    )


async def send_notification(notification: Notification) -> None:
    keyboard = None
    if notification.button:
        keyboard = build_claim_keyboard(
            source=notification.source, order_id=notification.order_id, shop_name=notification.shop_name
        )
    await send_tg_message_to_managers(text=notification.text, reply_markup=keyboard)
