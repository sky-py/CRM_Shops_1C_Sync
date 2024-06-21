from typing import Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from parse.parse_constants import *
from common_funcs import international_phone


class Client(BaseModel):
    id: int = Field(exclude=True)
    full_name: str
    name: str = Field(exclude=True)
    surname: str = Field(exclude=True)
    middlename: str = Field(exclude=True)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    bonus_points: int = Field(default=0, exclude=True)

    model_config = {
        'str_strip_whitespace': True
    }

    # @model_validator(mode='before')
    # def concatanate(cls, model):
    #     if model['surname']:
    #         model['name'] = model['surname'] + ' ' + model['name']
    #     return model

    @field_validator('phone')
    def normalize_phone(cls, value):
        return international_phone(value)


class Product(BaseModel):
    sku: Optional[str] = Field(default=None)
    name: Optional[str] = Field(default=None, alias='title')
    price: float = Field(default=0, alias='sale_price')
    quantity: int


class Shipping(BaseModel):
    shipping_receive_point: str = Field(default='', alias='full_delivery_address')


class Payment(BaseModel):
    payment_method_id: int
    amount: float
    status: str


class Utm(BaseModel):
    utm_source: str = Field(default='')


class Order(BaseModel):
    is_paid: bool = Field(alias='financial_status', exclude=True)
    source_id: Optional[int] = Field(default=None)
    source_uuid: int = Field(alias='number')
    manager_DB: Optional[int] = Field(default=None, exclude=True)
    manager_id: Optional[int] = Field(default=None)
    ordered_at: str = Field(alias='created_at')
    products: list[Product] = Field(alias='order_lines')
    discount_amount: float = Field(default=0, alias='discount')
    marketing: Utm = Field(alias='marketing')
    buyer: Client = Field(alias='client')
    buyer_comment: Optional[str] = Field(alias='comment', default=None)
    shipping: Shipping = Field(alias='shipping_address')
    payments: list[Payment]
    insales_id: int = Field(alias='id', exclude=True)
    total_price: float = Field(default=0, exclude=True)
    # status_id: int = Field(alias='custom_status', exclude=True)
    status_id: int = Field(alias='fulfillment_status', exclude=True)

    @model_validator(mode='before')
    def get_nested(cls, model):
        def process_names(name: str) -> str:
            return name.strip().capitalize() if name else ''

        if model['discount']:
            model['discount'] = model['discount']['full_amount']
        else:
            model['discount'] = 0

        if model.get('responsible_user_id'):
            model['manager_DB'] = manager_insales_to_db.get(model['responsible_user_id'])
        if model.get('manager_DB'):
            # model['manager_id'] = manager_db_id_to_CRM.get(model['manager_DB'])
            model['manager_id'] = get_key_by_value(manager_key_to_db, model['manager_DB'])

        model['marketing'] = {'utm_source': model['first_source']}

        model['financial_status'] = True if model.get('financial_status') == 'paid' else False

        model['fulfillment_status'] = status_insales_to_db.get(model['fulfillment_status'], Status.CANCELLED).value

        payment = dict()
        payment['payment_method_id'] = payment_insales_to_crm_id.get(model['payment_title'], 5)
        payment['amount'] = model['total_price']
        payment['status'] = 'paid' if model.get('financial_status') else 'not_paid'
        model['payments'] = [payment]

        model['client']['name'] = process_names(model['shipping_address']['name'])
        model['client']['surname'] = process_names(model['shipping_address']['surname'])
        model['client']['middlename'] = process_names(model['shipping_address']['middlename'])
        model['client']['full_name'] = f"{model['client']['surname']} {model['client']['name']} {model['client']['middlename']}"

        return model

    @field_validator('ordered_at')
    def format_date(cls, value):
        return value.split('.')[0].replace('T', ' ')

