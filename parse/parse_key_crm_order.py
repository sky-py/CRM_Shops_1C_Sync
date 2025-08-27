from typing import Optional
from common_funcs import international_phone
from parse.parse_constants import (
    Document1C,
    Status,
    Shops,
    PaymentStatus,
    manager_key_to_1c,
    manager_key_to_db,
    payment_crm_id_to_1c,
    shop_crm_id_to_sql_shop_id,
    shop_key_to_1c,
    status_key_group_to_db,
    paid_by_card_methods,
    TTN_SENT_BY_CAR
)
from parse.process_xml import get_name_and_category_by_sku
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tools.round import classic_round


class OrderKeyCrmShort(BaseModel):
    source_id: int
    key_crm_id: int = Field(alias='id')
    source_uuid: Optional[int] = None
    manager_id: Optional[int] = None
    status: Status = Field(alias='status_group_id')

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    def get_nested(cls, model):
        model = dict(model['context'].items())
        model['status_group_id'] = status_key_group_to_db.get(model['status_group_id'])
        model['manager_id'] = manager_key_to_db.get(model['manager_id'])
        return model


class ProductBuyer(BaseModel):
    sku: str = Field(default=None)
    name: str
    category: Optional[int] = Field(default=None)
    price: float = Field(default=0, alias='price_sold')
    quantity: float

    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    @field_validator('quantity')
    def convert(cls, value: str) -> int:
        return int(value)


class ProductSupplier(ProductBuyer):
    price: float = Field(default=0, alias='purchased_price')

    model_config = ConfigDict(populate_by_name=True)


class ProductCommissionProSale(ProductSupplier):
    sku: str = Field(default='Commission_Prosale')
    name: str = Field(default='Комиссия просейл')
    quantity: float = Field(default=1.0)


class ProductCommissionProSaleFreeDelivery(ProductSupplier):
    sku: str = Field(default='Commission_Prosale_free_delivery')
    name: str = Field(default='Комиссия просейл доставка')
    quantity: float = Field(default=1.0)
    
    
class ProductCommissionProSaleForOrder(ProductSupplier):
    sku: str = Field(default='Commission_Prosale_for_order')
    name: str = Field(default='Комиссия просейл за заказ')
    quantity: float = Field(default=1.0)


class FakeProductBuyer(ProductSupplier):
    sku: str = Field(default='Fake_Product')
    name: str = Field(default='Фиктивный товар')
    quantity: float = Field(default=1.0)
    price: float = Field(default=1.0)
    

class FakeProductSupplier(FakeProductBuyer):
    price: float = Field(default=0.5)


class Buyer(BaseModel):
    full_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    has_duplicates: bool = Field(exclude=True, default=False)

    # @field_validator('full_name')
    # def normalize(cls, value: str):
    #     try:
    #         new_name = reorder_names(value)
    #     except Exception as e:
    #         send_service_tg_message(str(e))
    #     else:
    #         return ' '.join([word.capitalize() for word in new_name.split(' ')]) if new_name else value


class Shipping(BaseModel):
    full_address: Optional[str] = None
    recipient_full_name: Optional[str] = None
    recipient_phone: Optional[str] = None


class Order1CBuyer(BaseModel):
    action: str = Field(default='create_buyer_order')
    document_type: Document1C = Field(default=Document1C.CLIENT_ORDER, exclude=True)
    proveden: bool = Field(default=False)
    key_crm_id: str = Field(alias='id')
    parent_id: Optional[str] = None
    stage_group_id: int = Field(alias='status_group_id', exclude=True)
    shop: Optional[str] = None  # shop name by 1C
    source_uuid: Optional[int] = Field(default=None, exclude=True)  # order id by back office
    manager: Optional[str] = None
    manager_comment: Optional[str] = None
    products: list[ProductBuyer]

    buyer: Optional[Buyer] = None
    supplier: Optional[str] = Field(default=None, exclude=True)
    shipping: Shipping
    payment: Optional[str] = None
    prices_rounded: bool = Field(default=False, exclude=True)

    shop_id: Optional[int] = Field(default=None, alias='source_id', exclude=True)  # shop id at CRM
    shop_sql_id: Optional[int] = Field(default=None, exclude=True)  # shop id at SQL DB
    push_to_1C: bool = Field(default=False, exclude=True)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    def get_nested(cls, model):
        model['id'] = str(model['id'])
        if model['parent_id']:
            model['parent_id'] = str(model['parent_id'])

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
            one_product_price = (model['products'][index]['price_sold'] -
                                 model['total_discount'] / float(model['products'][index]['quantity']))
            model['products'][index]['price_sold'] = classic_round(one_product_price, 2)

        for product in model['products']:
            if product['sku']:
                new_name, category = get_name_and_category_by_sku(product['sku'])
                if new_name:
                    product['name'] = new_name
                elif product['name'][:3].isupper():
                    product['name'] = product['name'].capitalize()
                product['category'] = category

        model['tracking_code'] = model['shipping']['tracking_code']

        for custom_field in model['custom_fields']:
            match custom_field['name']:
                case 'Постачальник':
                    model['supplier'] = custom_field['value'][0]
                case 'Номер постачальника':
                    model['supplier_id'] = custom_field['value']
                case 'Заказ 1С':
                    model['push_to_1C'] = custom_field['value']
                case 'Відправлено машиною':
                    if custom_field['value']:
                        model['tracking_code'] = TTN_SENT_BY_CAR

        paid_by_card = False
        payment_name_paid_by_card, payment_name_paid, payment_name_not_paid = None, None, None
        for payment in model.get('payments', []):
            p_name = payment_crm_id_to_1c.get(payment['payment_method_id'])
            if payment['status'] == PaymentStatus.PAID:
                if p_name in paid_by_card_methods:
                    paid_by_card = True
                    payment_name_paid_by_card = p_name
                else:
                    payment_name_paid = p_name
            else:
                payment_name_not_paid = p_name
         
        if (model['shop'] in [Shops.UKRSTIL.value, Shops.BEAUTY_MARKET.value, Shops.KRASUNIA.value] and
            payment_name_not_paid in paid_by_card_methods):
                payment_name_not_paid = None
        model['payment'] = (payment_name_paid_by_card or payment_name_paid or payment_name_not_paid)

        if not paid_by_card:
            for product in model['products']:
                quantity = float(product['quantity'])
                if (product['price_sold'] * quantity) % 1 != 0:
                    if quantity % 2 != 0:
                        product['price_sold'] = classic_round(product['price_sold'])
                    else:
                        product['price_sold'] = classic_round(product['price_sold'] * quantity) / quantity
                    model['prices_rounded'] = True

        return model


class Order1CSupplier(Order1CBuyer):
    action: str = Field(default='create_supplier_order')
    document_type: Document1C = Field(default=Document1C.SUPPLIER_ORDER, exclude=True)
    supplier: Optional[str] = None
    tracking_code: Optional[str] = None
    send_sms: bool = Field(default=True, exclude=True)
    supplier_id: Optional[str] = None
    products: list[ProductSupplier] = None

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
    key_crm_id: str
    parent_id: str
    shop: Optional[str] = None
    products: list[ProductSupplier]
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
