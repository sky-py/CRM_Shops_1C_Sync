import time
import json
from datetime import datetime, timedelta
from pathlib import Path
import constants
from api.key_crm_api import KeyCRM
from db.db_init import Session
from db.models import Order1CDB, PromOrderDB, PromCPARefundQueueDB
from db.sql_init import add_ttn_to_db
from parse.parse_key_crm_order import (
    Order1CBuyer, Order1CSupplier, Order1CSupplierUpdate, ProductBuyer,
    Order1CPostupleniye, Order1CSupplierPromCommissionOrder, Order1CReturnTovarov)
from send_sms import send_ttn_sms
from loguru import logger
from messengers import send_service_tg_message
from retry import retry


crm = KeyCRM(constants.KEY_CRM_API_KEY)
bad_orders = []
reload_file = Path(__file__).with_suffix('.reload')
Path(constants.json_orders_for_1c_path).mkdir(parents=True, exist_ok=True)
Path(constants.json_archive_1C_path).mkdir(parents=True, exist_ok=True)

logger.add(sink=f'log/{Path(__file__).stem}.log', format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='INFO', backtrace=True, diagnose=True)
logger.add(sink=lambda msg: send_service_tg_message(msg), format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}",
           level='ERROR')


def find_childs_products(crm_order: dict, all_orders: list[dict]) -> list[ProductBuyer]:
    children_products = []
    skus = [product['sku'] for product in crm_order['products']]
    for curr_order in all_orders:
        if curr_order['parent_id'] == crm_order['id']:    # found child of the order
            for product in curr_order['products']:
                if product['sku'] not in skus:
                    children_products.append(ProductBuyer(**product))
                    skus.append(product['sku'])
    return children_products


def create_json_file(order: Order1CBuyer | Order1CSupplierPromCommissionOrder | Order1CPostupleniye,
                     include_keys=None, exclude_keys=None):
    text = json.dumps(order.model_dump(mode='json', include=include_keys, exclude=exclude_keys),
                      ensure_ascii=False, indent=4)
    json_file = f'{order.key_crm_id}_{order.action}_{datetime.now().timestamp()}.json'
    (Path(constants.json_orders_for_1c_path) / json_file).write_text(data=text, encoding='utf-8')
    (Path(constants.json_archive_1C_path) / json_file).write_text(data=text, encoding='utf-8')
    if type(order) is not Order1CSupplierUpdate:
        logger.info(f'Created {order.document_type.value}, key_crm_id = {order.key_crm_id}')
    else:
        add_text = f'TTN to {order.tracking_code}' if order.tracking_code else f'Supplier_id to {order.supplier_id}'
        logger.info(f'Updated {add_text} for Supplier order, key_crm_id = {order.key_crm_id}')


def add_to_track_and_sms(order: Order1CSupplier):
    phone = order.buyer.phone if order.shipping.recipient_phone is None else order.shipping.recipient_phone
    fio = order.buyer.full_name if order.shipping.recipient_full_name is None else order.shipping.recipient_full_name
    if add_ttn_to_db(tracking_code=order.tracking_code,
                     shop_sql_id=order.shop_sql_id,
                     fio=fio,
                     phone=phone,
                     manager=order.manager):
        send_ttn_sms(phone=phone, tracking_code=order.tracking_code, shop_sql_id=order.shop_sql_id)


def format_date_time(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def make_time_interval(minutes: int) -> str:
    return f'{format_date_time(datetime.now() - timedelta(minutes=minutes))}, {format_date_time(datetime.now())}'


@retry(stop_after_delay=120)
def get_active_orders() -> list:
    orders = []
    r = crm.get_stages()['data']
    active_stages = [stage_dict['id'] for stage_dict in r if not stage_dict['is_closing_order']]
    # for stage in constants.KEY_ACTIVE_STAGES:
    for stage in active_stages:
        stage_orders = crm.get_orders(last_orders_amount=0, filter={'status_id': stage})
        print(f'{len(stage_orders)} orders for stage {stage}\n')
        orders += stage_orders
    return orders


@retry(stop_after_delay=120)
def get_completed_orders() -> list:
    orders = crm.get_orders(last_orders_amount=constants.KEY_GET_LAST_ACTIVE_ORDERS,
                            filter={'status_id': constants.order_completed_stage_id})
    print(f'{len(orders)} orders for Completed stage {constants.order_completed_stage_id}\n')
    return orders


@retry(stop_after_delay=120)
def get_last_modified_orders(minutes: int) -> list:
    my_filter = {'updated_between': make_time_interval(minutes + constants.KEY_TIME_SHIFT)}
    orders = crm.get_orders(last_orders_amount=0, filter=my_filter)
    print(f'{len(orders)} orders were modified during last {minutes} minutes (time shift = {constants.KEY_TIME_SHIFT})\n')
    return orders


def is_order_valid(order: Order1CBuyer) -> bool:
    """Checks if a client order is valid for processing."""
    return order.push_to_1C and order.manager and order.buyer and order.buyer.phone and not order.buyer.has_duplicates


def add_order_to_db(order: Order1CBuyer | Order1CSupplier | Order1CSupplierPromCommissionOrder):
    with Session.begin() as session:
        if type(order) is Order1CBuyer:
            session.add(Order1CDB(key_crm_id=order.key_crm_id,
                                  document_type=order.document_type))
        else:
            session.add(Order1CDB(key_crm_id=order.key_crm_id,
                                  parent_id=order.parent_id,
                                  document_type=order.document_type,
                                  tracking_code=order.tracking_code,
                                  supplier_id=order.supplier_id))


def process_new_buyer_order(order: Order1CBuyer):
    add_order_to_db(order)
    create_json_file(order)


def process_new_supplier_order(order: Order1CSupplier | Order1CSupplierPromCommissionOrder):
    if order.parent_id is None:
        order.parent_id = order.key_crm_id
    add_order_to_db(order)
    create_json_file(order, exclude_keys={'buyer', 'shipping', 'payment'})

    if order.tracking_code:
        add_to_track_and_sms(order)


def process_existing_supplier_order(order: Order1CSupplierUpdate, db_order: Order1CDB):
    if order.tracking_code and not db_order.tracking_code:  # but valid tracking code is not in db
        order.supplier_id = None
        db_order.tracking_code = order.tracking_code
        add_to_track_and_sms(order)
        create_json_file(order, include_keys={'action', 'key_crm_id', 'tracking_code', 'supplier_id'})
    elif order.supplier_id and not db_order.supplier_id:  # but valid supplier number is not in db
        order.tracking_code = None
        db_order.supplier_id = order.supplier_id
        create_json_file(order, include_keys={'action', 'key_crm_id', 'tracking_code', 'supplier_id'})


def process_new_supplier_cpa_comission_order(buyer_order: Order1CBuyer):
    with Session.begin() as session:
        prom_order = session.query(PromOrderDB).filter_by(order_id=buyer_order.source_uuid).first()
        if prom_order is not None and prom_order.cpa_commission > 0:
            commission_order = Order1CSupplierPromCommissionOrder(key_crm_id=prom_order.order_id,
                                                                  parent_id=buyer_order.key_crm_id,
                                                                  supplier=f'Просейл {prom_order.shop}',
                                                                  shop=prom_order.shop)
            commission_order.products[0].price = prom_order.cpa_commission
            process_new_supplier_order(commission_order)
            process_new_cpa_postupleniye(commission_order)


def process_new_cpa_postupleniye(commission_order: Order1CSupplierPromCommissionOrder):
    postupleniye = Order1CPostupleniye(key_crm_id=commission_order.key_crm_id,
                                       parent_id=commission_order.key_crm_id,
                                       supplier=commission_order.supplier)
    postupleniye.products[0].price = commission_order.products[0].price
    add_order_to_db(postupleniye)
    create_json_file(postupleniye)


def process_new_return_tovarov(record: PromCPARefundQueueDB):
    return_tovarov = Order1CReturnTovarov(key_crm_id=record.order_id,
                                          parent_id=record.order_id,
                                          supplier=f'Просейл {record.shop}')
    return_tovarov.products[0].price = record.cpa_commission
    add_order_to_db(return_tovarov)
    create_json_file(return_tovarov)


@logger.catch
def main():
    # crm_orders = crm.get_orders(last_orders_amount=constants.KEY_MAX_PROCESSING_ORDERS)
    # crm_orders = get_active_orders() + get_completed_orders()
    crm_orders = get_last_modified_orders(constants.KEY_TIME_INTERVAL_TO_CHECK)
    print(f'Got {len(crm_orders)} orders')
    if len(crm_orders) > constants.KEY_MAX_PROCESSING_ORDERS:
        raise Exception("Too many orders to process.")
    process_orders(crm_orders)
    process_cpa_refunds()


def process_orders(crm_orders: list):
    with Session.begin() as session:
        for order_dict in crm_orders:
            try:
                order = Order1CBuyer(**order_dict)
            except Exception as e:
                if order_dict['id'] not in bad_orders:
                    logger.error(f'Error {e} parsing order: {order_dict['id']}')
                    bad_orders.append(order_dict['id'])
                continue

            if not is_order_valid(order):
                continue  # skip some not properly filled orders

            if not order.parent_id:  # it is Buyer order and POSSIBLY Supplier order
                db_order = session.query(Order1CDB).filter_by(key_crm_id=order.key_crm_id, parent_id=None).first()
                if db_order is None:  # if order doesn't exist in db
                    for product in find_childs_products(order_dict, crm_orders):
                        order.products.append(product)  # adding child products to order
                    process_new_buyer_order(order)
                    process_new_supplier_cpa_comission_order(order)

            if order.supplier:   # Supplier present, this is a Supplier order or also a Supplier order
                order = Order1CSupplier(**order_dict)
                db_order = session.query(Order1CDB).filter(Order1CDB.key_crm_id == order.key_crm_id,
                                                           Order1CDB.parent_id.isnot(None)).first()
                if db_order is None:  # if order doesn't exist in db
                    process_new_supplier_order(order=order)
                else:  # if order exists in db
                    order = Order1CSupplierUpdate(**order_dict)
                    process_existing_supplier_order(order=order, db_order=db_order)


def process_cpa_refunds():

    with Session.begin() as session:
        all_cpa_refunds = session.query(PromCPARefundQueueDB).all()
        for cpa_refund in all_cpa_refunds:
            q = session.query(Order1CDB).filter_by(key_crm_id=cpa_refund.order_id).first()
            if q is not None:
                process_new_return_tovarov(cpa_refund)
                session.delete(cpa_refund)


if __name__ == '__main__':
    logger.info(f'STARTING {__file__}')
    while True:
        print(f'Getting CRM orders for 1C...')
        main()
        if reload_file.exists():
            reload_file.unlink(missing_ok=True)
            logger.info(f'SHUTTING DOWN {__file__}')
            exit(0)
        print(f'Sleeping {constants.time_to_sleep_crm_1c} sec\n')
        time.sleep(constants.time_to_sleep_crm_1c)
