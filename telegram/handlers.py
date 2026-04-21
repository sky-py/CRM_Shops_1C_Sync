import constants
from aiogram import F, Router
from aiogram.types import CallbackQuery
from parse.parse_constants import Shops
from telegram.sender import send_tg_message_to_managers
from telegram.service import claim_prom_order, claim_ukrsalon_order

router = Router()


@router.callback_query(F.data.startswith('claim:'))
async def claim_order_handler(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    manager_name = constants.managers.get(user_id)
    if manager_name is None:
        await callback.answer('У вас нет прав для принятия заказа.', show_alert=True)
        return

    parts = callback.data.split(':')

    source = parts[1]
    if source == 'ukrsalon' and len(parts) == 3:
        order_id = parts[2]
        result = await claim_ukrsalon_order(order_id, manager_name)
        order_title = f'заказ {order_id} на {Shops.UKRSALON.value}'
    elif source == 'prom' and len(parts) == 4:
        order_id = parts[2]
        try:
            shop_name = Shops[parts[3]].value
        except KeyError:
            await callback.answer('Неизвестный магазин.', show_alert=True)
            return
        result = await claim_prom_order(order_id, shop_name, manager_name)
        order_title = f'заказ {order_id} на {shop_name}'
    else:
        await callback.answer('Некорректные данные кнопки.', show_alert=True)
        return

    if result.status == 'accepted':
        await callback.answer()
        await send_tg_message_to_managers(f'{result.claimed_by_name} приняла {order_title}')
        return

    if result.status == 'already_claimed':
        await callback.answer(f'Этот заказ уже принят менеджером {result.claimed_by_name}', show_alert=True)
        return

    await callback.answer('Заказ не найден.', show_alert=True)
