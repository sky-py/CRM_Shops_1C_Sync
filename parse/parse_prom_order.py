import re
from typing import Optional
from pydantic.v1 import BaseModel, Field, root_validator, validator
from parse.parse_constants import *
from common_funcs import international_phone
from datetime import datetime


def get_price(price: str) -> float:
    return float(''.join(re.findall(r'[\d.]', price)))


class Product(BaseModel):
    sku: str
    name: str
    price: float = Field(default=0)
    quantity: int
    cpa_commission: float = Field(default=0)

    @root_validator(pre=True)
    def process_model(cls, model):
        model['price'] = get_price(model['price']) if model.get('price') else 0
        model['cpa_commission'] = float(model['cpa_commission']['amount']) if model.get('cpa_commission') else 0
        return model


class Buyer(BaseModel):
    name: str = Field(exclude=True)
    middlename: str = Field(exclude=True)
    surname: str = Field(exclude=True)
    full_name: str
    phone: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    buyer_comment: Optional[str] = Field(exclude=True)

    class Config:
        anystr_strip_whitespace = True


class Shipping(BaseModel):
    full_address: Optional[str] = Field(default=None)


class OrderProm(BaseModel):
    order_id: int = Field(alias='id')
    status: PromStatus
    date_created: datetime
    buyer: Buyer = Field(alias='client')
    total_price: float = Field(alias='price', default=0)
    cpa_commission: float = Field(default=0)
    cpa_is_refunded: bool
    products: list[Product]
    shipping: Shipping

    shop: Optional[str]    # shop name by 1C
    manager: Optional[str]

    @root_validator(pre=True)
    def get_nested(cls, model):
        def process_names(name: str) -> str:
            return name.strip().capitalize() if name else ''

        model['status'] = status_prom_to_db.get(model['status'], PromStatus.OTHER)
        model['price'] = get_price(model['price']) if model.get('price') else 0
        model['cpa_is_refunded'] = model['cpa_commission']['is_refunded'] if (model.get('cpa_commission') and model.get('cpa_commission').get('is_refunded')) else False
        model['cpa_commission'] = float(model['cpa_commission']['amount']) if model.get('cpa_commission') else 0

        model['client'] = dict()
        model['client']['phone'] = international_phone(model.get('phone', ''))
        model['client']['email'] = model.get('email', '')
        model['client']['buyer_comment'] = model.get('client_notes', '')
        model['client']['name'] = process_names(model.get('client_first_name', ''))
        model['client']['middlename'] = process_names(model.get('client_second_name', ''))
        model['client']['surname'] = process_names(model.get('client_last_name', ''))
        model['client']['full_name'] = (f'{model['client']['surname']} '
                                        f'{model['client']['name']} '
                                        f'{model['client']['middlename']}')

        model['shipping'] = dict()
        model['shipping']['full_address'] = model.get('delivery_address', '')

        return model
