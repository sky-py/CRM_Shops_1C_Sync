from typing import Optional
from pydantic import BaseModel, Field, model_validator, field_validator
from parse.parse_constants import *
from parse.process_xml import get_name_by_sku
from common_funcs import international_phone


class OrderKeyCrmShort(BaseModel):
    source_id: int
    key_crm_id: int = Field(alias='id')
    source_uuid: Optional[int] = None
    manager_id: Optional[int] = None
    status: Status = Field(alias='status_group_id')

    @model_validator(mode='before')
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

    @field_validator('quantity')
    def convert(cls, value: str):
        return int(value)

    @field_validator('price')
    def round_low(cls, value):
        return value // 1


class ProductSupplier(ProductBuyer):
    price: float = Field(default=0, alias='purchased_price')

    @field_validator('price')
    def round_low(cls, value):
        return value


class Buyer(BaseModel):
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    has_duplicates: bool = Field(exclude=True, default=False)


class Shipping(BaseModel):
    full_address: Optional[str] = None
    recipient_full_name: Optional[str] = None
    recipient_phone: Optional[str] = None


class Order1CBuyer(BaseModel):
    action: str = Field(default='create_buyer_order')
    document_type: Document1C = Field(default=Document1C.CLIENT_ORDER, exclude=True)
    proveden: bool = Field(default=False)
    key_crm_id: int = Field(alias='id')
    parent_id: Optional[int] = None
    shop: Optional[str] = None  # shop name by 1C
    source_uuid: Optional[int] = Field(default=None, exclude=True)  # order id by back office
    manager: Optional[str] = None
    manager_comment: Optional[str] = None
    products: list[ProductBuyer]

    buyer: Optional[Buyer] = None
    supplier: Optional[str] = Field(default=None, exclude=True)
    shipping: Shipping
    payment: Optional[str] = None

    shop_id: Optional[int] = Field(default=None, alias='source_id', exclude=True)  # shop id at CRM
    shop_sql_id: Optional[int] = Field(default=None, exclude=True)  # shop id at SQL DB
    push_to_1C: bool = Field(default=False, exclude=True)

    model_config = {
        'debug': True,
    }

    @model_validator(mode='before')
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
    tracking_code: Optional[str] = None
    supplier_id: Optional[str] = None
    products: list[ProductSupplier] = None

    @model_validator(mode='before')
    def get_nested_2(cls, model):
        model['tracking_code'] = model['shipping']['tracking_code']
        return model

    @field_validator('tracking_code')
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
    shop: Optional[str] = None
    products: list[ProductSupplier] = Field(default_factory=lambda: [ProductSupplier(sku='Commission_Prosale',
                                                                     name='Комиссия просейл',
                                                                     quantity=1.0)])
    manager: str = Field(default='Финансист')
    manager_comment: Optional[str] = None
    tracking_code: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier: str


class Order1CPostupleniye(Order1CSupplierPromCommissionOrder):
    action: str = Field(default='create_postupleniye_tovarov')
    document_type: Document1C = Field(default=Document1C.POSTUPLENIYE_TOVAROV, exclude=True)


class Order1CReturnTovarov(Order1CSupplierPromCommissionOrder):
    action: str = Field(default='create_return_tovarov')
    document_type: Document1C = Field(default=Document1C.RETURN_TOVAROV, exclude=True)

