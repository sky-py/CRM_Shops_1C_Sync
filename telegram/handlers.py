import constants
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message
from loguru import logger
from parse.parse_constants import Shops
from telegram.sender import send_tg_message_to_managers
from telegram.service import claim_prom_order, claim_ukrsalon_order

router = Router()


async def safe_answer_callback(callback: CallbackQuery, *args, **kwargs) -> None:
    try:
        await callback.answer(*args, **kwargs)
    except TelegramBadRequest as e:
        if 'query is too old' in str(e):
            logger.info(f'Callback answer skipped: {e}')
        else:
            logger.exception(f'Error answering callback: {e}')


@router.callback_query(F.data.startswith('claim:'))
async def claim_order_handler(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    manager_name = constants.managers.get(user_id)
    if manager_name is None:
        await safe_answer_callback(callback, 'У вас нет прав для принятия заказа.', show_alert=True)
        return

    parts = callback.data.split(':')

    source = parts[1]
    if source == 'ukrsalon' and len(parts) == 4:
        try:
            order_id = int(parts[2])
            source_uuid = parts[3]
        except ValueError:
            await safe_answer_callback(callback, 'Некорректный номер заказа.', show_alert=True)
            return
        result = await claim_ukrsalon_order(order_id, manager_name)
        order_title = f'заказ {source_uuid} на {Shops.UKRSALON.value}'
    elif source == 'prom' and len(parts) == 4:
        try:
            order_id = int(parts[2])
        except ValueError:
            await safe_answer_callback(callback, 'Некорректный номер заказа.', show_alert=True)
            return
        try:
            shop_name = Shops[parts[3]].value
        except KeyError:
            await safe_answer_callback(callback, 'Неизвестный магазин.', show_alert=True)
            return
        result = await claim_prom_order(order_id, shop_name, manager_name)
        order_title = f'заказ {order_id} на {shop_name}'
    else:
        await safe_answer_callback(callback, 'Некорректные данные кнопки.', show_alert=True)
        return

    if result.status == 'accepted':
        await safe_answer_callback(callback)
        await send_tg_message_to_managers(f'{result.claimed_by_name} приняла {order_title}')
        return

    if result.status == 'already_claimed':
        await safe_answer_callback(
            callback,
            f'Этот заказ уже принят менеджером {result.claimed_by_name} в {result.claimed_at.strftime("%H:%M:%S")}.',
            show_alert=True,
        )
        return

    await safe_answer_callback(callback, 'Заказ не найден.', show_alert=True)


@router.message()
async def log_message_handler(message: Message) -> None:
    content = message.text or message.caption or '<no text>'
    logger.info(
        f'Unexpected bot message from {message.from_user.id} ({message.from_user.full_name}) '
        f'[{message.content_type}]: {content}'
    )
