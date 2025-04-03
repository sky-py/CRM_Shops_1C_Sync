import re
from datetime import datetime
from typing import Optional
from common_funcs import international_phone
from loguru import logger
from parse.parse_constants import PromStatus, status_prom_to_db
from pydantic import BaseModel, Field, model_validator


def get_price(price: str) -> float:
    return float(''.join(re.findall(r'[\d.,]', price)).replace(',', '.'))


class Product(BaseModel):
    sku: str
    name: str
    price: float = Field(default=0)
    quantity: int
    cpa_commission: float = Field(default=0)

    @model_validator(mode='before')
    def process_model(cls, model):
        model['price'] = get_price(model['price']) if model.get('price') else 0
        model['cpa_commission'] = float(model['cpa_commission']['amount']) if model.get('cpa_commission') else 0
        return model


class Buyer(BaseModel):
    name: str = Field(exclude=True)
    middlename: str = Field(exclude=True)
    surname: str = Field(exclude=True)
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    buyer_comment: Optional[str] = Field(exclude=True)

    model_config = {'str_strip_whitespace': True}


class Shipping(BaseModel):
    full_address: Optional[str] = None


class OrderProm(BaseModel):
    order_id: int = Field(alias='id')
    status: PromStatus
    date_created: datetime
    buyer: Buyer = Field(alias='client')
    total_price: float = Field(alias='price', default=0)
    cpa_commission: float = Field(default=0)
    cpa_is_refunded: bool  # if CPA returned to us
    delivery_commision: float = Field(default=0)  # we pay this amount for free delivery
    products: list[Product]
    shipping: Shipping

    shop: Optional[str] = None  # shop name by 1C
    manager: Optional[str] = None

    @model_validator(mode='before')
    def get_nested(cls, model):
        def process_names(name: str) -> str:
            return name.strip().capitalize() if name else ''

        model['status'] = status_prom_to_db.get(model['status'], PromStatus.OTHER)
        model['price'] = get_price(model['price']) if model.get('price') else 0

        model['cpa_is_refunded'] = bool(model.get('cpa_commission') and model.get('cpa_commission').get('is_refunded'))
        model['cpa_commission'] = float(model.get('cpa_commission', {}).get('amount', 0))

        if model['has_order_promo_free_delivery']:
            try:
                match = re.search(r'([\d.]+) грн — продавец', model['ps_promotion']['conditions'][0])
                model['delivery_commision'] = float(match.group(1))  # type: ignore
            except Exception as e:
                logger.error(f'Promo free delivery conditions not found at order {model["id"]}: {e}')

        model['client'] = {}
        model['client']['phone'] = international_phone(model.get('phone', ''))
        model['client']['email'] = model.get('email', '')
        model['client']['buyer_comment'] = model.get('client_notes', '')
        model['client']['name'] = process_names(model.get('client_first_name', ''))
        model['client']['middlename'] = process_names(model.get('client_second_name', ''))
        model['client']['surname'] = process_names(model.get('client_last_name', ''))
        model['client']['full_name'] = (
            f'{model["client"]["surname"]} {model["client"]["name"]} {model["client"]["middlename"]}'
        )

        model['shipping'] = {}
        model['shipping']['full_address'] = model.get('delivery_address', '')

        return model
