from typing import Optional
from pydantic import BaseModel, Field, model_validator
from parse.parse_constants import *
from common_funcs import international_phone
from datetime import datetime


class Product(BaseModel):
    sku: str = Field(alias='article')
    name: str = Field(alias='title')
    price: float = Field(default=0)
    quantity: int


class Buyer(BaseModel):
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    buyer_comment: Optional[str] = Field(exclude=True)


class Shipping(BaseModel):
    full_address: Optional[str] = None


class OrderHoroshop(BaseModel):
    order_id: int
    status: PromStatus
    total_price: float = Field(alias='total_sum', default=0)
    date_created: datetime = Field(alias='stat_created')
    buyer: Buyer = Field(alias='client')
    products: list[Product]
    shipping: Shipping

    shop: Optional[str] = None    # shop name by 1C
    manager: Optional[str] = None

    @model_validator(mode='before')
    def get_nested(cls, model):
        def process_names(name: str) -> str:
            return ' '.join(map(lambda n: n.strip().capitalize(), name.split())) if name else ''

        model['status'] = status_horoshop_to_db.get(model['stat_status'], PromStatus.OTHER)

        model['client'] = dict()
        model['client']['phone'] = international_phone(model.get('delivery_phone', ''))
        model['client']['email'] = model.get('delivery_email', '')
        model['client']['buyer_comment'] = model.get('comment', '')
        model['client']['full_name'] = process_names(model.get('delivery_name', ''))

        model['shipping'] = dict()
        model['shipping']['full_address'] = model.get('delivery_address', '')

        return model
