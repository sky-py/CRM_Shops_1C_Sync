from typing import Optional
from pydantic.v1 import BaseModel, Field, root_validator, validator
from parse.parse_constants import *
from parse.process_xml import get_name_by_sku
from common_funcs import international_phone


class OrderKeyCrmShort(BaseModel):
    source_id: int
    key_crm_id: int = Field(alias='id')
    source_uuid: Optional[int]
    manager_id: Optional[int]
    status: Status = Field(alias='status_group_id')

    @root_validator(pre=True)
    def get_nested(cls, model):
        model = {k: v for k, v in model['context'].items()}
        model['status_group_id'] = status_key_group_to_db.get(model['status_group_id'])
        model['manager_id'] = manager_key_to_db.get(model['manager_id'])
        return model


class ProductBuyer(BaseModel):
    sku: str = Field(default=None)
    name: str
    price: float = Field(default=0, alias='price_sold')
    # purchased_price: float = Field(default=0, exclude=True)
    quantity: float

    @validator('quantity')
    def convert(cls, value: str):
        return int(value)

    @validator('price')
    def round_low(cls, value):
        return value // 1


class ProductSupplier(ProductBuyer):
    price: float = Field(default=0, alias='purchased_price')

    @validator('price')
    def round_low(cls, value):
        return value


class Buyer(BaseModel):
    full_name: str
    phone: Optional[str]
    email: Optional[str]
    has_duplicates: bool = Field(exclude=True, default=False)


class Shipping(BaseModel):
    full_address: Optional[str]
    recipient_full_name: Optional[str]
    recipient_phone: Optional[str]


class Order1CBuyer(BaseModel):
    action: str = Field(default='create_buyer_order')
    document_type: Document1C = Field(default=Document1C.CLIENT_ORDER, exclude=True)
    proveden: bool = Field(default=False)
    key_crm_id: int = Field(alias='id')
    parent_id: Optional[int]
    shop: Optional[str]  # shop name by 1C
    source_uuid: Optional[int] = Field(exclude=True)  # order id by back office
    manager: Optional[str]
    manager_comment: Optional[str]
    products: list[ProductBuyer]

    buyer: Optional[Buyer]
    supplier: Optional[str] = Field(exclude=True)
    shipping: Shipping
    payment: Optional[str]

    shop_id: Optional[int] = Field(alias='source_id', exclude=True)  # shop id at CRM
    shop_sql_id: Optional[int] = Field(exclude=True)  # shop id at SQL DB
    push_to_1C: bool = Field(default=False, exclude=True)

    class Config:
        debug = True
        error_message_template = "Field '{field}' {msg}"

    @root_validator(pre=True)
    def get_nested(cls, model):
        model['shop'] = shop_key_to_1c.get(model['source_id'])

        model['shop_sql_id'] = shop_crm_id_to_sql_shop_id.get(model['source_id'], 1)

        if model['buyer']:
            model['buyer']['phone'] = international_phone(model['buyer']['phone'])
            model['shipping']['recipient_phone'] = international_phone(model['shipping']['recipient_phone'])
            if model['shipping']['recipient_phone'] == model['buyer']['phone']:
                model['shipping']['recipient_full_name'] = None
                model['shipping']['recipient_phone'] = None
            model['buyer']['has_duplicates'] = model['buyer']['has_duplicates'] > 0

        model['manager'] = model['manager'] and manager_key_to_1c.get(model['manager']['id'])

        if model['total_discount']:
            prices = [product['price_sold'] for product in model['products']]
            index = prices.index(max(prices))
            model['products'][index]['price_sold'] = \
                model['products'][index]['price_sold'] - round(model['total_discount'] / float(model['products'][index]['quantity']), 2)

        for product in model['products']:
            if product['sku']:
                if new_name := get_name_by_sku(product['sku']):
                    product['name'] = new_name
                elif product['name'][:3].isupper():
                    product['name'] = product['name'].capitalize()

        for custom_field in model['custom_fields']:
            if custom_field['name'] == 'Постачальник':
                model['supplier'] = custom_field['value'][0]
            if custom_field['name'] == 'Номер постачальника':
                model['supplier_id'] = custom_field['value']
            if custom_field['name'] == 'Заказ 1С':
                model['push_to_1C'] = custom_field['value']

        if model['payments']:
            model['payment'] = payment_crm_id_to_1c.get(model['payments'][0]['payment_method_id'], None)

        return model


class Order1CSupplier(Order1CBuyer):
    action: str = Field(default='create_supplier_order')
    document_type: Document1C = Field(default=Document1C.SUPPLIER_ORDER, exclude=True)
    supplier: str
    tracking_code: Optional[str]
    supplier_id: Optional[str]
    products: list[ProductSupplier]

    @root_validator(pre=True)
    def get_nested_2(cls, model):
        model['tracking_code'] = model['shipping']['tracking_code']
        return model

    @validator('tracking_code')
    def check_tracking_code(cls, value):
        if value is not None and len(value) < 5:
            return None
        else:
            return value


class Order1CSupplierUpdate(Order1CSupplier):
    action: str = Field(default='update_supplier_order')


class Order1CSupplierPromCommissionOrder(BaseModel):
    action: str = Field(default='create_supplier_order')
    document_type: Document1C = Field(default=Document1C.SUPPLIER_ORDER, exclude=True)
    proveden: bool = Field(default=True)
    key_crm_id: int
    parent_id: int
    shop: Optional[str]
    products: list[ProductSupplier] = Field(default=[ProductSupplier(sku='Commission_Prosale',
                                                                     name='Комиссия просейл',
                                                                     price=0,
                                                                     quantity=1.0)])
    manager: str = Field(default='Финансист')
    manager_comment: Optional[str]
    tracking_code: Optional[str]
    supplier_id: Optional[str]
    supplier: str


class Order1CPostupleniye(Order1CSupplierPromCommissionOrder):
    action: str = Field(default='create_postupleniye_tovarov')
    document_type: Document1C = Field(default=Document1C.POSTUPLENIYE_TOVAROV, exclude=True)


class Order1CReturnTovarov(Order1CSupplierPromCommissionOrder):
    action: str = Field(default='create_return_tovarov')
    document_type: Document1C = Field(default=Document1C.RETURN_TOVAROV, exclude=True)
