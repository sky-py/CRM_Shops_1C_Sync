from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from parse.parse_constants import Shops


def build_claim_keyboard(source: str, order_id: int, shop_name: str) -> InlineKeyboardMarkup:
    if source == 'ukrsalon':
        callback_data = f'claim:ukrsalon:{order_id}'
    elif source == 'prom':
        callback_data = f'claim:prom:{order_id}:{Shops(shop_name).name}'
    else:
        raise ValueError(f'Unsupported claim source: {source}')

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Принять', callback_data=callback_data)],
        ]
    )
